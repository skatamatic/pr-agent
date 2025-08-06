import difflib
import os
import re
from typing import Optional, Tuple
from urllib.parse import urlparse

from pr_agent.algo.types import EDIT_TYPE, FilePatchInfo

from ..algo.file_filter import filter_ignored
from ..algo.language_handler import is_valid_file
from ..algo.utils import (PRDescriptionHeader, clip_tokens,
                          find_line_number_of_relevant_line_in_file,
                          load_large_diff)
from ..config_loader import get_settings
from ..log import get_logger
from .git_provider import GitProvider
import json

AZURE_DEVOPS_AVAILABLE = True
ADO_APP_CLIENT_DEFAULT_ID = "499b84ac-1321-427f-aa17-267ca6975798/.default"
MAX_PR_DESCRIPTION_AZURE_LENGTH = 4000-1

try:
    # noinspection PyUnresolvedReferences
    from azure.devops.connection import Connection
    # noinspection PyUnresolvedReferences
    from azure.devops.released.git import (Comment, CommentThread, GitPullRequest, GitVersionDescriptor, GitClient, CommentThreadContext, CommentPosition)
    # noinspection PyUnresolvedReferences
    from azure.identity import DefaultAzureCredential
    from msrest.authentication import BasicAuthentication
    # Only log if we have a logger available
    try:
        get_logger().info("Azure DevOps SDK imports successful")
    except:
        pass  # Logger might not be available during import
except ImportError as e:
    AZURE_DEVOPS_AVAILABLE = False
    # Only log if we have a logger available
    try:
        get_logger().error(f"Azure DevOps provider disabled due to missing dependencies: {e}")
        get_logger().error("Install azure-devops package: pip install azure-devops")
    except:
        print(f"Azure DevOps provider disabled due to missing dependencies: {e}")
        print("Install azure-devops package: pip install azure-devops")


class AzureDevopsProvider(GitProvider):
    
    def _debug_suggestion_structure(self, suggestion: dict, idx: int):
        """Helper method to deeply debug suggestion structures"""
        get_logger().info(f"🔍 AZURE DEBUG: ====== DEEP SUGGESTION ANALYSIS #{idx + 1} ======")
        
        try:
            # Pretty print the full suggestion structure
            suggestion_json = json.dumps(suggestion, indent=2, default=str)
            get_logger().info(f"🔍 AZURE DEBUG: Full suggestion structure:")
            get_logger().info(f"🔍 AZURE DEBUG: {suggestion_json}")
        except Exception as e:
            get_logger().warning(f"🔍 AZURE DEBUG: Could not serialize suggestion to JSON: {e}")
        
        # Check for potential sources of duplication
        body = suggestion.get('body', '')
        if body:
            # Look for repeated lines or patterns
            lines = body.split('\n')
            get_logger().info(f"🔍 AZURE DEBUG: Body has {len(lines)} lines")
            
            # Check for line duplication
            seen_lines = {}
            duplicates = []
            for i, line in enumerate(lines):
                stripped = line.strip()
                if stripped and len(stripped) > 5:  # Ignore very short lines
                    if stripped in seen_lines:
                        duplicates.append((i, line, seen_lines[stripped]))
                    else:
                        seen_lines[stripped] = i
            
            if duplicates:
                get_logger().warning(f"🔍 AZURE DEBUG: Found {len(duplicates)} potential duplicate lines in body:")
                for line_num, line_content, first_occurrence in duplicates:
                    get_logger().warning(f"🔍 AZURE DEBUG: Line {line_num} (first at {first_occurrence}): {repr(line_content)}")
            else:
                get_logger().info(f"🔍 AZURE DEBUG: No obvious line duplicates found in body")
                
            # Check specific patterns that might indicate duplication
            if '```suggestion' in body and '```diff' in body:
                get_logger().warning(f"🔍 AZURE DEBUG: Body contains BOTH suggestion and diff blocks - potential conversion issue!")
            
            # Look for repeated code blocks
            code_blocks = []
            in_code_block = False
            current_block = []
            block_type = None
            
            for line in lines:
                if line.strip().startswith('```'):
                    if not in_code_block:
                        in_code_block = True
                        block_type = line.strip()
                        current_block = [line]
                    else:
                        current_block.append(line)
                        code_blocks.append((block_type, '\n'.join(current_block)))
                        in_code_block = False
                        current_block = []
                        block_type = None
                elif in_code_block:
                    current_block.append(line)
            
            get_logger().info(f"🔍 AZURE DEBUG: Found {len(code_blocks)} code blocks")
            for i, (block_type, block_content) in enumerate(code_blocks):
                get_logger().info(f"🔍 AZURE DEBUG: Code block {i + 1} ({block_type}): {len(block_content)} chars")
                
        get_logger().info(f"🔍 AZURE DEBUG: ====== END DEEP ANALYSIS #{idx + 1} ======")

    def __init__(
            self, pr_url: Optional[str] = None, incremental: Optional[bool] = False
    ):
        if not AZURE_DEVOPS_AVAILABLE:
            raise ImportError(
                "Azure DevOps provider is not available. Please install the required dependencies."
            )

        self.azure_devops_client = self._get_azure_devops_client()
        self.diff_files = None
        self.workspace_slug = None
        self.repo_slug = None
        self.repo = None
        self.pr_num = None
        self.pr = None
        self.temp_comments = []
        self.incremental = incremental
        if pr_url:
            self.set_pr(pr_url)

    def publish_code_suggestions(self, code_suggestions: list) -> bool:
        """
        Publishes code suggestions as comments on the PR.
        """
        post_parameters_list = []
        for idx, suggestion in enumerate(code_suggestions):
            if not suggestion:  # Skip None suggestions
                get_logger().warning(f"Skipping None suggestion #{idx + 1}")
                continue
            
            body = suggestion['body']
            original_suggestion = suggestion.get('original_suggestion', None)
            
            # Check if suggestion is commit-eligible - only convert non-commit-eligible suggestions to diff format
            is_commit_eligible = original_suggestion.get('commit_eligible', True) if original_suggestion else True
            
            # Add comprehensive logging to understand what data we're sending to Azure DevOps
            get_logger().info(f"=== AZURE SUGGESTION DEBUG #{idx + 1} ===")
            get_logger().info(f"Original suggestion data structure:")
            get_logger().info(f"  - commit_eligible: {original_suggestion.get('commit_eligible') if original_suggestion else 'N/A'}")
            get_logger().info(f"  - has existing_code: {bool(original_suggestion and original_suggestion.get('existing_code')) if original_suggestion else False}")
            get_logger().info(f"  - has improved_code: {bool(original_suggestion and original_suggestion.get('improved_code')) if original_suggestion else False}")
            
            if original_suggestion and original_suggestion.get('existing_code'):
                existing_code = original_suggestion['existing_code']
                get_logger().info(f"EXISTING_CODE ({len(existing_code)} chars):")
                get_logger().info(f"'{existing_code}'")
                get_logger().info(f"EXISTING_CODE lines: {existing_code.split(chr(10))}")
            
            if original_suggestion and original_suggestion.get('improved_code'):
                improved_code = original_suggestion['improved_code']
                get_logger().info(f"IMPROVED_CODE ({len(improved_code)} chars):")
                get_logger().info(f"'{improved_code}'")
                get_logger().info(f"IMPROVED_CODE lines: {improved_code.split(chr(10))}")
            
            get_logger().info(f"SUGGESTION BODY being sent to Azure:")
            get_logger().info(f"'{body}'")
            
            # Extract the content within the suggestion block to see exactly what Azure will display
            suggestion_match = re.search(r'```suggestion\n(.*?)\n```', body, re.DOTALL)
            if suggestion_match:
                suggestion_content = suggestion_match.group(1)
                get_logger().info(f"SUGGESTION BLOCK CONTENT (what Azure will show literally):")
                get_logger().info(f"'{suggestion_content}'")
                get_logger().info(f"SUGGESTION BLOCK lines: {suggestion_content.split(chr(10))}")
            
            # Handle Azure DevOps suggestions differently based on commit eligibility
            if original_suggestion and original_suggestion.get('existing_code') and original_suggestion.get('improved_code'):
                try:
                    existing_code = original_suggestion['existing_code'].rstrip() + "\n"
                    improved_code = original_suggestion['improved_code'].rstrip() + "\n"
                    
                    if not is_commit_eligible:
                        # For NON-commit-eligible suggestions, convert to diff format to avoid duplication
                        diff = difflib.unified_diff(existing_code.split('\n'),
                                                    improved_code.split('\n'), n=999)
                        patch_orig = "\n".join(diff)
                        patch = "\n".join(patch_orig.splitlines()[5:]).strip('\n')
                        diff_code = f"\n\n```diff\n{patch.rstrip()}\n```"
                        
                        # replace ```suggestion ... ``` with diff_code, using regex:
                        body = re.sub(r'```suggestion.*?```', diff_code, body, flags=re.DOTALL)
                        get_logger().info(f"Converted non-commit-eligible suggestion #{idx + 1} to diff format")
                    else:
                        # For COMMIT-ELIGIBLE suggestions, keep ```suggestion format but optimize content
                        # Azure DevOps shows both line context AND suggestion content, causing duplication
                        # Solution: Only show the NEW/CHANGED lines in the suggestion block
                        
                        # Create a clean diff to identify what's actually changing
                        diff_lines = list(difflib.unified_diff(
                            existing_code.split('\n'),
                            improved_code.split('\n'),
                            n=0,  # No context lines in the diff
                            lineterm=''
                        ))
                        
                        # Extract only the added lines (lines that start with '+')
                        added_lines = []
                        for line in diff_lines:
                            if line.startswith('+') and not line.startswith('+++'):
                                added_lines.append(line[1:])  # Remove the '+' prefix
                        
                        if added_lines:
                            # Replace suggestion content with only the new/changed lines
                            clean_suggestion_content = '\n'.join(added_lines)
                            body = re.sub(
                                r'```suggestion\n(.*?)\n```', 
                                f'```suggestion\n{clean_suggestion_content}\n```', 
                                body, 
                                flags=re.DOTALL
                            )
                            get_logger().info(f"Optimized commit-eligible suggestion #{idx + 1} content (showing only new lines)")
                        else:
                            get_logger().info(f"No changes detected for commit-eligible suggestion #{idx + 1}, keeping original")
                    
                except Exception as e:
                    get_logger().exception(f"Failed to process suggestion #{idx + 1}, error: {e}")
            
            relevant_file = suggestion['relevant_file']
            relevant_lines_start = suggestion['relevant_lines_start']
            relevant_lines_end = suggestion['relevant_lines_end']

            if not relevant_lines_start or relevant_lines_start == -1:
                get_logger().warning(
                    f"Failed to publish code suggestion, relevant_lines_start is {relevant_lines_start}")
                continue

            if relevant_lines_end < relevant_lines_start:
                get_logger().warning(f"Failed to publish code suggestion, "
                                       f"relevant_lines_end is {relevant_lines_end} and "
                                       f"relevant_lines_start is {relevant_lines_start}")
                continue

            # Calculate the proper end offset - should be the length of the last line
            end_line_offset = 9999  # Default fallback - use large number to span to end of line
            if original_suggestion and original_suggestion.get('existing_code'):
                existing_code = original_suggestion['existing_code']
                # Split by newlines and handle trailing empty lines properly
                existing_lines = existing_code.split('\n')
                
                # Remove empty lines from the end (caused by trailing newlines)
                while existing_lines and not existing_lines[-1]:
                    existing_lines.pop()
                
                if existing_lines:
                    # Get the actual last line with content
                    last_line = existing_lines[-1]
                    end_line_offset = len(last_line) + 1  # +1 for end of line position
                    get_logger().info(f"THREAD CONTEXT: Last line '{last_line}' (length={len(last_line)}), using offset={end_line_offset}")
                else:
                    get_logger().info(f"THREAD CONTEXT: No non-empty lines found in existing_code, using default offset={end_line_offset}")
            else:
                get_logger().info(f"THREAD CONTEXT: No existing_code available, using default offset={end_line_offset}")
            
            thread_context = CommentThreadContext(
                file_path=relevant_file,
                right_file_start=CommentPosition(offset=1, line=relevant_lines_start),
                right_file_end=CommentPosition(offset=end_line_offset, line=relevant_lines_end))
            
            comment = Comment(content=body, comment_type=1)
            thread = CommentThread(comments=[comment], thread_context=thread_context)
            
            # Log the exact payload being sent to Azure DevOps API
            get_logger().info(f"AZURE API PAYLOAD for suggestion #{idx + 1}:")
            get_logger().info(f"  - Comment content length: {len(body)} chars")
            get_logger().info(f"  - Comment content: '{body}'")
            get_logger().info(f"  - Thread context: {thread_context}")
            get_logger().info(f"  - Project: {self.workspace_slug}")
            get_logger().info(f"  - Repository: {self.repo_slug}")
            get_logger().info(f"  - PR ID: {self.pr_num}")
            
            try:
                api_response = self.azure_devops_client.create_thread(
                    comment_thread=thread,
                    project=self.workspace_slug,
                    repository_id=self.repo_slug,
                    pull_request_id=self.pr_num
                )
                get_logger().info(f"AZURE API RESPONSE for suggestion #{idx + 1}: {api_response}")
                get_logger().info(f"=== END AZURE SUGGESTION DEBUG #{idx + 1} ===\n")
            except Exception as e:
                get_logger().error(f"Azure failed to publish code suggestion #{idx + 1}, error: {e}")
        return True

    def reply_to_comment_from_comment_id(self, comment_id: int, body: str, is_temporary: bool = False) -> Comment:
        # comment_id is actually thread_id
        return self.reply_to_thread(comment_id, body, is_temporary)

    def get_pr_description_full(self) -> str:
        return self.pr.description

    def edit_comment(self, comment: Comment, body: str):
        try:
            self.azure_devops_client.update_comment(
                repository_id=self.repo_slug,
                pull_request_id=self.pr_num,
                thread_id=comment.thread_id,
                comment_id=comment.id,
                comment=Comment(content=body),
                project=self.workspace_slug,
            )
        except Exception as e:
            get_logger().exception(f"Failed to edit comment, error: {e}")

    def remove_comment(self, comment: Comment):
        try:
            self.azure_devops_client.delete_comment(
                repository_id=self.repo_slug,
                pull_request_id=self.pr_num,
                thread_id=comment.thread_id,
                comment_id=comment.id,
                project=self.workspace_slug,
            )
        except Exception as e:
            get_logger().exception(f"Failed to remove comment, error: {e}")

    def publish_labels(self, pr_types):
        try:
            for pr_type in pr_types:
                self.azure_devops_client.create_pull_request_label(
                    label={"name": pr_type},
                    project=self.workspace_slug,
                    repository_id=self.repo_slug,
                    pull_request_id=self.pr_num,
                )
        except Exception as e:
            get_logger().warning(f"Failed to publish labels, error: {e}")

    def get_pr_labels(self, update=False):
        try:
            labels = self.azure_devops_client.get_pull_request_labels(
                project=self.workspace_slug,
                repository_id=self.repo_slug,
                pull_request_id=self.pr_num,
            )
            return [label.name for label in labels]
        except Exception as e:
            get_logger().exception(f"Failed to get labels, error: {e}")
            return []

    def is_supported(self, capability: str) -> bool:
        return True

    def set_pr(self, pr_url: str):
        self.pr_url = pr_url
        self.workspace_slug, self.repo_slug, self.pr_num = self._parse_pr_url(pr_url)
        self.pr = self._get_pr()

    def get_repo_settings(self):
        try:
            contents = self.azure_devops_client.get_item_content(
                repository_id=self.repo_slug,
                project=self.workspace_slug,
                download=False,
                include_content_metadata=False,
                include_content=True,
                path=".pr_agent.toml",
            )
            return list(contents)[0]
        except Exception as e:
            if get_settings().config.verbosity_level >= 2:
                get_logger().error(f"Failed to get repo settings, error: {e}")
            return ""

    def get_files(self):
        files = []
        for i in self.azure_devops_client.get_pull_request_commits(
                project=self.workspace_slug,
                repository_id=self.repo_slug,
                pull_request_id=self.pr_num,
        ):
            changes_obj = self.azure_devops_client.get_changes(
                project=self.workspace_slug,
                repository_id=self.repo_slug,
                commit_id=i.commit_id,
            )

            for c in changes_obj.changes:
                files.append(c["item"]["path"])
        return list(set(files))

    def get_diff_files(self) -> list[FilePatchInfo]:
        try:

            if self.diff_files:
                return self.diff_files

            base_sha = self.pr.last_merge_target_commit
            head_sha = self.pr.last_merge_source_commit

            # Get PR iterations
            try:
                iterations = self.azure_devops_client.get_pull_request_iterations(
                    repository_id=self.repo_slug,
                    pull_request_id=self.pr_num,
                    project=self.workspace_slug
                )
            except Exception as e:
                get_logger().warning(f"Failed to get PR iterations, falling back to basic method: {e}")
                iterations = None
            
            changes = None
            if iterations:
                iteration_id = iterations[-1].id  # Get the last iteration (most recent changes)

                # Get changes for the iteration  
                try:
                    changes = self.azure_devops_client.get_pull_request_iteration_changes(
                        repository_id=self.repo_slug,
                        pull_request_id=self.pr_num,
                        iteration_id=iteration_id,
                        project=self.workspace_slug
                    )
                except Exception as e:
                    get_logger().warning(f"Failed to get PR iteration changes: {e}")
                    changes = None
            diff_files = []
            diffs = []
            diff_types = {}
            if changes:
                for change in changes.change_entries:
                    item = change.additional_properties.get('item', {})
                    path = item.get('path', None)
                    if path:
                        diffs.append(path)
                        diff_types[path] = change.additional_properties.get('changeType', 'Unknown')

            # wrong implementation - gets all the files that were changed in any commit in the PR
            # commits = self.azure_devops_client.get_pull_request_commits(
            #     project=self.workspace_slug,
            #     repository_id=self.repo_slug,
            #     pull_request_id=self.pr_num,
            # )
            #
            # diff_files = []
            # diffs = []
            # diff_types = {}

            # for c in commits:
            #     changes_obj = self.azure_devops_client.get_changes(
            #         project=self.workspace_slug,
            #         repository_id=self.repo_slug,
            #         commit_id=c.commit_id,
            #     )
            #     for i in changes_obj.changes:
            #         if i["item"]["gitObjectType"] == "tree":
            #             continue
            #         diffs.append(i["item"]["path"])
            #         diff_types[i["item"]["path"]] = i["changeType"]
            #
            # diffs = list(set(diffs))

            diffs_original = diffs
            diffs = filter_ignored(diffs_original, 'azure')
            if diffs_original != diffs:
                try:
                    get_logger().info(f"Filtered out [ignore] files for pull request:", extra=
                    {"files": diffs_original,  # diffs is just a list of names
                     "filtered_files": diffs})
                except Exception:
                    pass

            invalid_files_names = []
            for file in diffs:
                if not is_valid_file(file):
                    invalid_files_names.append(file)
                    continue

                version = GitVersionDescriptor(
                    version=head_sha.commit_id, version_type="commit"
                )
                try:
                    new_file_content_str = self.azure_devops_client.get_item(
                        repository_id=self.repo_slug,
                        path=file,
                        project=self.workspace_slug,
                        version_descriptor=version,
                        download=False,
                        include_content=True,
                    )

                    new_file_content_str = new_file_content_str.content
                except Exception as error:
                    get_logger().error(f"Failed to retrieve new file content of {file} at version {version}", error=error)
                    # get_logger().error(
                    #     "Failed to retrieve new file content of %s at version %s. Error: %s",
                    #     file,
                    #     version,
                    #     str(error),
                    # )
                    new_file_content_str = ""

                edit_type = EDIT_TYPE.MODIFIED
                if diff_types[file] == "add":
                    edit_type = EDIT_TYPE.ADDED
                elif diff_types[file] == "delete":
                    edit_type = EDIT_TYPE.DELETED
                elif "rename" in diff_types[file]: # diff_type can be `rename` | `edit, rename`
                    edit_type = EDIT_TYPE.RENAMED

                version = GitVersionDescriptor(
                    version=base_sha.commit_id, version_type="commit"
                )
                if edit_type == EDIT_TYPE.ADDED or edit_type == EDIT_TYPE.RENAMED:
                    original_file_content_str = ""
                else:
                    try:
                        original_file_content_str = self.azure_devops_client.get_item(
                            repository_id=self.repo_slug,
                            path=file,
                            project=self.workspace_slug,
                            version_descriptor=version,
                            download=False,
                            include_content=True,
                        )
                        original_file_content_str = original_file_content_str.content
                    except Exception as error:
                        get_logger().error(f"Failed to retrieve original file content of {file} at version {version}", error=error)
                        original_file_content_str = ""

                patch = load_large_diff(
                    file, new_file_content_str, original_file_content_str, show_warning=False
                ).rstrip()

                # count number of lines added and removed
                patch_lines = patch.splitlines(keepends=True)
                num_plus_lines = len([line for line in patch_lines if line.startswith('+')])
                num_minus_lines = len([line for line in patch_lines if line.startswith('-')])

                diff_files.append(
                    FilePatchInfo(
                        original_file_content_str,
                        new_file_content_str,
                        patch=patch,
                        filename=file,
                        edit_type=edit_type,
                        num_plus_lines=num_plus_lines,
                        num_minus_lines=num_minus_lines,
                    )
                )
            get_logger().info(f"Invalid files: {invalid_files_names}")

            self.diff_files = diff_files
            return diff_files
        except Exception as e:
            get_logger().exception(f"Failed to get diff files, error: {e}")
            return []

    def publish_comment(self, pr_comment: str, is_temporary: bool = False, thread_context=None) -> Comment:
        if is_temporary and not get_settings().config.publish_output_progress:
            get_logger().debug(f"Skipping publish_comment for temporary comment: {pr_comment}")
            return None
        comment = Comment(content=pr_comment)
        thread = CommentThread(comments=[comment], thread_context=thread_context, status="closed")
        thread_response = self.azure_devops_client.create_thread(
            comment_thread=thread,
            project=self.workspace_slug,
            repository_id=self.repo_slug,
            pull_request_id=self.pr_num,
        )
        created_comment = thread_response.comments[0]
        created_comment.thread_id = thread_response.id
        if is_temporary:
            self.temp_comments.append(created_comment)
        return created_comment

    def publish_persistent_comment(self, pr_comment: str,
                                   initial_header: str,
                                   update_header: bool = True,
                                   name='review',
                                   final_update_message=True):
        return self.publish_persistent_comment_full(pr_comment, initial_header, update_header, name, final_update_message)

    def publish_description(self, pr_title: str, pr_body: str):
        if len(pr_body) > MAX_PR_DESCRIPTION_AZURE_LENGTH:

            usage_guide_text='<details> <summary><strong>✨ Describe tool usage guide:</strong></summary><hr>'
            ind = pr_body.find(usage_guide_text)
            if ind != -1:
                pr_body = pr_body[:ind]

            if len(pr_body) > MAX_PR_DESCRIPTION_AZURE_LENGTH:
                changes_walkthrough_text = PRDescriptionHeader.CHANGES_WALKTHROUGH.value
                ind = pr_body.find(changes_walkthrough_text)
                if ind != -1:
                    pr_body = pr_body[:ind]

            if len(pr_body) > MAX_PR_DESCRIPTION_AZURE_LENGTH:
                trunction_message = " ... (description truncated due to length limit)"
                pr_body = pr_body[:MAX_PR_DESCRIPTION_AZURE_LENGTH - len(trunction_message)] + trunction_message
                get_logger().warning("PR description was truncated due to length limit")
        try:
            updated_pr = GitPullRequest()
            updated_pr.title = pr_title
            updated_pr.description = pr_body
            self.azure_devops_client.update_pull_request(
                project=self.workspace_slug,
                repository_id=self.repo_slug,
                pull_request_id=self.pr_num,
                git_pull_request_to_update=updated_pr,
            )
        except Exception as e:
            get_logger().exception(
                f"Could not update pull request {self.pr_num} description: {e}"
            )

    def remove_initial_comment(self):
        try:
            for comment in self.temp_comments:
                self.remove_comment(comment)
        except Exception as e:
            get_logger().exception(f"Failed to remove temp comments, error: {e}")

    def publish_inline_comment(self, body: str, relevant_file: str, relevant_line_in_file: str, original_suggestion=None):
        self.publish_inline_comments([self.create_inline_comment(body, relevant_file, relevant_line_in_file)])

    def create_inline_comment(self, body: str, relevant_file: str, relevant_line_in_file: str,
                              absolute_position: int = None):
        position, absolute_position = find_line_number_of_relevant_line_in_file(self.get_diff_files(),
                                                                                relevant_file.strip('`'),
                                                                                relevant_line_in_file,
                                                                                absolute_position)
        if position == -1:
            if get_settings().config.verbosity_level >= 2:
                get_logger().info(f"Could not find position for {relevant_file} {relevant_line_in_file}")
            subject_type = "FILE"
        else:
            subject_type = "LINE"
        path = relevant_file.strip()
        return dict(body=body, path=path, position=position, absolute_position=absolute_position) if subject_type == "LINE" else {}

    def publish_inline_comments(self, comments: list[dict], disable_fallback: bool = False):
            overall_success = True
            for comment in comments:
                try:
                    self.publish_comment(comment["body"],
                                        thread_context={
                                            "filePath": comment["path"],
                                            "rightFileStart": {
                                                "line": comment["absolute_position"],
                                                "offset": comment["position"],
                                            },
                                            "rightFileEnd": {
                                                "line": comment["absolute_position"],
                                                "offset": comment["position"],
                                            },
                                        })
                    if get_settings().config.verbosity_level >= 2:
                        get_logger().info(
                            f"Published code suggestion on {self.pr_num} at {comment['path']}"
                        )
                except Exception as e:
                    if get_settings().config.verbosity_level >= 2:
                        get_logger().error(f"Failed to publish code suggestion, error: {e}")
                    overall_success = False
            return overall_success

    def get_title(self):
        return self.pr.title

    def get_languages(self):
        languages = []
        files = self.azure_devops_client.get_items(
            project=self.workspace_slug,
            repository_id=self.repo_slug,
            recursion_level="Full",
            include_content_metadata=True,
            include_links=False,
            download=False,
        )
        for f in files:
            if f.git_object_type == "blob":
                file_name, file_extension = os.path.splitext(f.path)
                languages.append(file_extension[1:])

        extension_counts = {}
        for ext in languages:
            if ext != "":
                extension_counts[ext] = extension_counts.get(ext, 0) + 1

        total_extensions = sum(extension_counts.values())

        extension_percentages = {
            ext: (count / total_extensions) * 100
            for ext, count in extension_counts.items()
        }

        return extension_percentages

    def get_pr_branch(self):
        try:
            pr_info = self.azure_devops_client.get_pull_request_by_id(
                project=self.workspace_slug, pull_request_id=self.pr_num
            )
            if pr_info and pr_info.source_ref_name:
                # Azure DevOps branch refs are like "refs/heads/feature-branch"
                source_branch = pr_info.source_ref_name.split("/")[-1]
                return source_branch
            else:
                get_logger().warning("PR info or source_ref_name is None")
                return "main"  # fallback
        except Exception as e:
            get_logger().error(f"Failed to get PR branch: {e}")
            return "main"  # fallback

    def get_user_id(self):
        return 0

    def get_issue_comments(self) -> list[Comment]:
        threads = self.azure_devops_client.get_threads(repository_id=self.repo_slug, pull_request_id=self.pr_num, project=self.workspace_slug)
        threads.reverse()
        comment_list = []
        for thread in threads:
            for comment in thread.comments:
                if comment.content and comment not in comment_list:
                    comment.body = comment.content
                    comment.thread_id = thread.id
                    comment_list.append(comment)
        return comment_list

    def add_eyes_reaction(self, issue_comment_id: int, disable_eyes: bool = False) -> Optional[int]:
        return True

    def remove_reaction(self, issue_comment_id: int, reaction_id: int) -> bool:
        return True

    def set_like(self, thread_id: int, comment_id: int, create: bool = True):
        if create:
            self.azure_devops_client.create_like(self.repo_slug, self.pr_num, thread_id, comment_id, project=self.workspace_slug)
        else:
            self.azure_devops_client.delete_like(self.repo_slug, self.pr_num, thread_id, comment_id, project=self.workspace_slug)
            
    def set_thread_status(self, thread_id: int, status: str):
        try:
            self.azure_devops_client.update_thread(CommentThread(status=status), self.repo_slug, self.pr_num, thread_id, self.workspace_slug)
        except Exception as e:
            get_logger().exception(f"Failed to set thread status, error: {e}")
            
    def reply_to_thread(self, thread_id: int, body: str, is_temporary: bool = False) -> Comment:
        try:
            comment = Comment(content=body)
            response = self.azure_devops_client.create_comment(comment, self.repo_slug, self.pr_num, thread_id, self.workspace_slug)
            response.thread_id = thread_id
            if is_temporary:
                self.temp_comments.append(response)
            return response
        except Exception as e:
            get_logger().exception(f"Failed to reply to thread, error: {e}")
    
    def get_thread_context(self, thread_id: int) -> CommentThreadContext:
        try:
            thread = self.azure_devops_client.get_pull_request_thread(self.repo_slug, self.pr_num, thread_id, self.workspace_slug)
            return thread.thread_context
        except Exception as e:
            get_logger().exception(f"Failed to set thread status, error: {e}")
    
    @staticmethod
    def _parse_pr_url(pr_url: str) -> Tuple[str, str, int]:
        parsed_url = urlparse(pr_url)
        path_parts = parsed_url.path.strip("/").split("/")
        num_parts = len(path_parts)
        if num_parts < 5:
            raise ValueError("The provided URL has insufficient path components for an Azure DevOps PR URL")
        
        # Verify that the second-to-last path component is "pullrequest"
        if path_parts[num_parts - 2] != "pullrequest":
            raise ValueError("The provided URL does not follow the expected Azure DevOps PR URL format")

        workspace_slug = path_parts[num_parts - 5]
        repo_slug = path_parts[num_parts - 3]
        try:
            pr_number = int(path_parts[num_parts - 1])
        except ValueError as e:
            raise ValueError("Cannot parse PR number in the provided URL") from e

        return workspace_slug, repo_slug, pr_number

    @staticmethod
    def _get_azure_devops_client() -> GitClient:
        org = get_settings().azure_devops.get("org", None)
        pat = get_settings().azure_devops.get("pat", None)

        if not org:
            raise ValueError("Azure DevOps organization is required")

        if pat:
            auth_token = pat
        else:
            try:
                # try to use azure default credentials
                # see https://learn.microsoft.com/en-us/python/api/overview/azure/identity-readme?view=azure-python
                # for usage and env var configuration of user-assigned managed identity, local machine auth etc.
                get_logger().info("No PAT found in settings, trying to use Azure Default Credentials.")
                credentials = DefaultAzureCredential()
                accessToken = credentials.get_token(ADO_APP_CLIENT_DEFAULT_ID)
                auth_token = accessToken.token
            except Exception as e:
                get_logger().error(f"No PAT found in settings, and Azure Default Authentication failed, error: {e}")
                raise

        credentials = BasicAuthentication("", auth_token)

        credentials = BasicAuthentication("", auth_token)
        azure_devops_connection = Connection(base_url=org, creds=credentials)
        azure_devops_client = azure_devops_connection.clients.get_git_client()

        return azure_devops_client

    def _get_repo(self):
        if self.repo is None:
            self.repo = self.azure_devops_client.get_repository(
                project=self.workspace_slug, repository_id=self.repo_slug
            )
        return self.repo

    def _get_pr(self):
        self.pr = self.azure_devops_client.get_pull_request_by_id(
            pull_request_id=self.pr_num, project=self.workspace_slug
        )
        return self.pr

    def get_commit_messages(self):
        return ""  # not implemented yet

    def get_pr_id(self):
        try:
            pr_id = f"{self.workspace_slug}/{self.repo_slug}/{self.pr_num}"
            return pr_id
        except Exception as e:
            if get_settings().config.verbosity_level >= 2:
                get_logger().info(f"Failed to get PR id, error: {e}")
            return ""

    def publish_file_comments(self, file_comments: list) -> bool:
        pass

    def get_line_link(self, relevant_file: str, relevant_line_start: int, relevant_line_end: int = None) -> str:
        return self.pr_url+f"?_a=files&path={relevant_file}"

    def get_comment_url(self, comment) -> str:
        return self.pr_url + "?discussionId=" + str(comment.thread_id)

    def get_pr_file_content(self, file_path: str, branch: str) -> str:
        """
        Retrieves the content of a file from the specified branch in Azure DevOps.
        
        Args:
            file_path: Path to the file in the repository
            branch: Branch name to retrieve the file from
            
        Returns:
            File content as string, or empty string if file not found or error occurs
        """
        try:
            # Handle common branch references
            version_descriptor = None
            if branch == "HEAD" or not branch:
                # Use the source branch of the current PR
                pr_info = self.azure_devops_client.get_pull_request_by_id(
                    project=self.workspace_slug, pull_request_id=self.pr_num
                )
                branch_ref = pr_info.source_ref_name
            else:
                # Construct the branch reference (Azure DevOps expects refs/heads/branch_name format)
                if not branch.startswith("refs/"):
                    branch_ref = f"refs/heads/{branch}"
                else:
                    branch_ref = branch
            
            # Create version descriptor for the branch
            version_descriptor = GitVersionDescriptor(
                version_type="branch",
                version=branch_ref
            )
            
            # Get file content from Azure DevOps
            contents = self.azure_devops_client.get_item_content(
                repository_id=self.repo_slug,
                project=self.workspace_slug,
                download=False,
                include_content_metadata=False,
                include_content=True,
                path=file_path,
                version_descriptor=version_descriptor
            )
            
            # Convert the response to string
            if contents:
                # contents is typically a generator/iterator
                content_bytes = b''.join(contents)
                return content_bytes.decode('utf-8')
            else:
                return ""
                
        except Exception as e:
            if get_settings().config.verbosity_level >= 2:
                get_logger().debug(f"Could not load {file_path} from branch {branch}: {e}")
            return ""

    def get_latest_commit_url(self) -> str:
        commits = self.azure_devops_client.get_pull_request_commits(self.repo_slug, self.pr_num, self.workspace_slug)
        last = commits[0]
        url = self.azure_devops_client.normalized_url + "/" + self.workspace_slug + "/_git/" + self.repo_slug + "/commit/" + last.commit_id
        return url
    