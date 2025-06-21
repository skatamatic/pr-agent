"""
Test Data Generation Module for Developer Tools
"""
import random
import uuid
from datetime import datetime, timedelta
from typing import Dict, Any
from database import SessionLocal
from models import OperationDB, LogEntryDB


def _get_realistic_error(command: str) -> str:
    """Generate realistic error messages based on command type"""
    error_templates = {
        "review": [
            "AI model rate limit exceeded during review analysis",
            "Failed to parse diff: malformed patch format",
            "Context window exceeded: PR too large for analysis",
            "GitHub API authentication failed during file retrieval",
            "Timeout occurred while processing complex code changes"
        ],
        "describe": [
            "Unable to extract meaningful summary from PR changes",
            "GitHub API rate limit hit while fetching PR metadata", 
            "Failed to analyze commit messages: encoding error",
            "PR description generation timeout after 120 seconds",
            "Insufficient context: no meaningful code changes detected"
        ],
        "improve": [
            "Static analysis failed: unsupported file format detected",
            "AI model refused to process: potential security violation",
            "Code improvement suggestions timeout during generation",
            "Failed to parse AST: syntax errors in target files",
            "Memory limit exceeded during code analysis"
        ],
        "test": [
            "Test framework detection failed for target language",
            "Unable to generate meaningful test cases: insufficient context",
            "Compilation errors in generated test code",
            "Test generation timeout: complex business logic detected",
            "Mocking framework compatibility issues detected"
        ],
        "add_docs": [
            "Documentation template not found for detected framework",
            "API signature extraction failed: complex type annotations",
            "Markdown generation error: invalid character encoding",
            "Documentation standards validation failed",
            "Unable to infer documentation scope from changes"
        ],
        "update_changelog": [
            "Changelog format not recognized or unsupported",
            "Version detection failed: no semantic versioning found",
            "Failed to categorize changes: ambiguous commit messages",
            "Changelog update conflict with existing entries",
            "Release notes generation timeout exceeded"
        ]
    }
    
    return random.choice(error_templates.get(command, [
        "Unknown error occurred during operation processing",
        "Operation failed due to unexpected system state",
        "Processing interrupted by resource constraints"
    ]))


def _generate_realistic_log_sequence(operation) -> list:
    """Generate realistic log sequence for an operation"""
    logs = []
    command = operation.command
    status = operation.status
    
    # Always start with initialization
    logs.append(("INFO", f"Starting {command} operation for {operation.repo}", "pr_agent.core", "handle_request"))
    logs.append(("DEBUG", f"Operation ID: {operation.operation_id}, Request ID: {operation.request_id}", "pr_agent.core", "handle_request"))
    
    # Authentication and setup
    logs.append(("INFO", f"Authenticating with GitHub for repository {operation.repo}", "pr_agent.git_provider", "authenticate"))
    logs.append(("DEBUG", f"Installation ID: {operation.installation_id}, Sender: {operation.sender}", "pr_agent.git_provider", "get_installation"))
    
    # Fetch PR data
    logs.append(("INFO", f"Fetching PR data from {operation.pr_url}", "pr_agent.git_provider", "get_pr_data"))
    logs.append(("DEBUG", f"Retrieved PR metadata: title, body, and file list", "pr_agent.git_provider", "get_pr_data"))
    
    # Command-specific logs
    if command == "review":
        logs.extend([
            ("INFO", "Analyzing code changes for review", "pr_agent.tools.reviewer", "analyze_pr"),
            ("DEBUG", "Extracting diff hunks and file modifications", "pr_agent.algo.git_processing", "process_diff"),
            ("INFO", "Running static code analysis", "pr_agent.tools.reviewer", "static_analysis"),
            ("DEBUG", f"Found {random.randint(3, 12)} files to review", "pr_agent.tools.reviewer", "count_files"),
            ("INFO", "Generating AI-powered review comments", "pr_agent.tools.reviewer", "generate_review"),
            ("DEBUG", f"AI processing took {random.uniform(5, 25):.2f} seconds", "pr_agent.ai.handler", "process_request")
        ])
    
    elif command == "describe":
        logs.extend([
            ("INFO", "Analyzing PR for description generation", "pr_agent.tools.describer", "analyze_pr"),
            ("DEBUG", "Extracting commit messages and change patterns", "pr_agent.algo.git_processing", "analyze_commits"),
            ("INFO", "Detecting PR type and scope", "pr_agent.tools.describer", "detect_pr_type"),
            ("DEBUG", f"Detected PR type: {random.choice(['feature', 'bugfix', 'refactor', 'docs'])}", "pr_agent.tools.describer", "detect_pr_type"),
            ("INFO", "Generating PR description", "pr_agent.tools.describer", "generate_description")
        ])
    
    elif command == "improve":
        logs.extend([
            ("INFO", "Scanning code for improvement suggestions", "pr_agent.tools.improver", "analyze_code"),
            ("DEBUG", "Running linting and style analysis", "pr_agent.tools.improver", "run_linters"),
            ("WARNING", f"Found {random.randint(0, 3)} potential code smells", "pr_agent.tools.improver", "detect_issues"),
            ("INFO", "Generating improvement suggestions", "pr_agent.tools.improver", "generate_suggestions"),
            ("DEBUG", f"Generated {random.randint(1, 8)} improvement suggestions", "pr_agent.tools.improver", "generate_suggestions")
        ])
    
    elif command == "test":
        logs.extend([
            ("INFO", "Analyzing code for test generation", "pr_agent.tools.tester", "analyze_code"),
            ("DEBUG", f"Detected language: {random.choice(['Python', 'JavaScript', 'TypeScript', 'Java'])}", "pr_agent.tools.tester", "detect_language"),
            ("INFO", "Identifying testable functions and classes", "pr_agent.tools.tester", "find_testable_code"),
            ("DEBUG", f"Found {random.randint(2, 6)} testable components", "pr_agent.tools.tester", "find_testable_code"),
            ("INFO", "Generating unit tests", "pr_agent.tools.tester", "generate_tests")
        ])
    
    # Add status-specific endings
    if status == "completed":
        logs.extend([
            ("INFO", f"Successfully completed {command} operation", "pr_agent.core", "finalize_operation"),
            ("DEBUG", f"Generated output with {random.randint(1, 5)} sections", "pr_agent.core", "finalize_operation"),
            ("INFO", f"Publishing results to GitHub PR", "pr_agent.git_provider", "post_comment")
        ])
    
    elif status == "failed":
        error_msg = _get_realistic_error(command)
        logs.extend([
            ("ERROR", error_msg, f"pr_agent.tools.{command}er", "process"),
            ("WARNING", "Operation failed, attempting cleanup", "pr_agent.core", "handle_error"),
            ("ERROR", f"Operation {operation.operation_id} terminated with errors", "pr_agent.core", "finalize_operation")
        ])
    
    elif status in ["processing", "fetching_context", "self_reflecting", "publishing"]:
        # In-progress operations
        if status == "fetching_context":
            logs.append(("INFO", "Fetching additional context from repository", "pr_agent.context", "fetch_context"))
        elif status == "self_reflecting":
            logs.append(("INFO", "AI model performing self-reflection on generated content", "pr_agent.ai.handler", "self_reflect"))
        elif status == "publishing":
            logs.append(("INFO", "Preparing to publish results to GitHub", "pr_agent.git_provider", "prepare_comment"))
    
    # Add some random system logs
    if random.random() < 0.3:  # 30% chance
        logs.append(("DEBUG", f"Memory usage: {random.randint(45, 95)}MB", "pr_agent.system", "monitor_resources"))
    
    if random.random() < 0.2:  # 20% chance
        logs.append(("WARNING", f"Rate limit remaining: {random.randint(100, 4000)} requests", "pr_agent.git_provider", "check_rate_limit"))
    
    return logs


async def generate_test_data() -> Dict[str, Any]:
    """Generate sample operations and logs for testing"""
    db = None
    try:
        db = SessionLocal()
        
        operations_created = 0
        logs_created = 0
        
        # Enhanced test data with more realistic scenarios
        test_repos = [
            "microsoft/vscode", "facebook/react", "google/tensorflow", 
            "vercel/next.js", "nodejs/node", "microsoft/TypeScript",
            "angular/angular", "vuejs/vue", "webpack/webpack", "babel/babel"
        ]
        
        test_commands = [
            {"cmd": "review", "weight": 4},
            {"cmd": "describe", "weight": 3}, 
            {"cmd": "improve", "weight": 2},
            {"cmd": "test", "weight": 1},
            {"cmd": "add_docs", "weight": 1},
            {"cmd": "update_changelog", "weight": 1}
        ]
        
        test_senders = [
            "alice-dev", "bob-reviewer", "charlie-maintainer", 
            "diana-contributor", "eve-tester", "frank-architect"
        ]
        
        status_scenarios = [
            {"status": "completed", "weight": 6},
            {"status": "failed", "weight": 2},
            {"status": "processing", "weight": 1},
            {"status": "fetching_context", "weight": 1},
            {"status": "self_reflecting", "weight": 1},
            {"status": "publishing", "weight": 1}
        ]
        
        for i in range(12):  # Generate more operations
            operation_id = f"op-{uuid.uuid4().hex[:8]}"
            started_time = datetime.utcnow() - timedelta(
                minutes=random.randint(5, 2880)  # Up to 2 days ago
            )
            
            # Weighted random selection
            repo = random.choice(test_repos)
            command = random.choices(
                [cmd["cmd"] for cmd in test_commands],
                weights=[cmd["weight"] for cmd in test_commands]
            )[0]
            status = random.choices(
                [s["status"] for s in status_scenarios],
                weights=[s["weight"] for s in status_scenarios]
            )[0]
            sender = random.choice(test_senders)
            
            # Create realistic operation
            operation = OperationDB(
                operation_id=operation_id,
                command=command,
                repo=repo,
                pr_url=f"https://github.com/{repo}/pull/{random.randint(1000, 9999)}",
                status=status,
                started_at=started_time,
                last_updated=datetime.utcnow(),
                completed_at=datetime.utcnow() if status in ["completed", "failed"] else None,
                duration=random.uniform(15, 300) if status in ["completed", "failed"] else None,
                error_details=_get_realistic_error(command) if status == "failed" else None,
                installation_id=f"inst_{random.randint(100000, 999999)}",
                sender=sender,
                request_id=f"req_{uuid.uuid4().hex[:12]}",
                response_time=random.uniform(0.3, 8.0),
                context_fetch_time=random.uniform(0.1, 3.0),
                ai_processing_time=random.uniform(3.0, 45.0),
                suggestions_count=random.randint(2, 15) if status == "completed" and command in ["review", "improve"] else None,
                errors_count=random.randint(0, 2),
                warnings_count=random.randint(0, 4)
            )
            
            db.add(operation)
            operations_created += 1
            
            # Generate realistic linked logs for this operation
            log_messages = _generate_realistic_log_sequence(operation)
            
            for j, (level, message, module, function) in enumerate(log_messages):
                log_time = started_time + timedelta(seconds=j * random.randint(2, 15))
                
                log_entry = LogEntryDB(
                    timestamp=log_time,
                    level=level,
                    message=message,
                    module=module,
                    function=function,
                    line=random.randint(25, 800),
                    pr_url=operation.pr_url,
                    command=operation.command,
                    installation_id=operation.installation_id,
                    repo=operation.repo,
                    sender=operation.sender,
                    request_id=operation.request_id,
                    status=operation.status,
                    analytics=random.choice([True, False]),
                    app_name="pr-agent",
                    git_provider="github"
                )
                
                db.add(log_entry)
                logs_created += 1
        
        # Generate some unlinked logs (system-level logs)
        for i in range(8):
            log_time = datetime.utcnow() - timedelta(minutes=random.randint(1, 180))
            level = random.choice(["INFO", "WARNING", "ERROR", "DEBUG"])
            
            system_messages = [
                "System health check completed successfully",
                "Database connection pool optimization completed", 
                "Configuration reload triggered by admin",
                "WebSocket connection established with dashboard",
                "Rate limit exceeded for API key, throttling requests",
                "Cache invalidation triggered for repository metadata",
                "Background cleanup task removed 45 expired sessions",
                "Security scan detected no vulnerabilities in dependencies"
            ]
            
            log_entry = LogEntryDB(
                timestamp=log_time,
                level=level,
                message=random.choice(system_messages),
                module="system",
                function=random.choice(["health_check", "cleanup", "security", "cache"]),
                line=random.randint(10, 200),
                analytics=False,
                app_name="pr-agent",
                git_provider="system"
            )
            
            db.add(log_entry)
            logs_created += 1
        
        db.commit()
        db.close()
        
        return {
            "status": "success",
            "message": f"Generated {operations_created} test operations and {logs_created} test logs with realistic linking",
            "data": {"operations": operations_created, "logs": logs_created}
        }
        
    except Exception as e:
        if db:
            db.rollback()
            db.close()
        return {"status": "error", "message": f"Failed to generate test data: {str(e)}"}


async def simulate_live_activity() -> Dict[str, Any]:
    """Simulate a live operation in progress with linked logs"""
    try:
        db = SessionLocal()
        
        operation_id = f"live-op-{uuid.uuid4().hex[:8]}"
        demo_repos = ["microsoft/vscode", "facebook/react", "nodejs/node"]
        demo_commands = ["review", "describe", "improve"]
        demo_users = ["alice-dev", "bob-maintainer", "carol-contributor"]
        
        repo = random.choice(demo_repos)
        command = random.choice(demo_commands)
        user = random.choice(demo_users)
        
        operation = OperationDB(
            operation_id=operation_id,
            command=command,
            repo=repo,
            pr_url=f"https://github.com/{repo}/pull/{random.randint(1000, 5000)}",
            status="processing",
            started_at=datetime.utcnow() - timedelta(seconds=random.randint(15, 120)),
            last_updated=datetime.utcnow(),
            installation_id=f"live_{random.randint(100000, 999999)}",
            sender=user,
            request_id=f"live_{uuid.uuid4().hex[:12]}",
            response_time=random.uniform(0.3, 2.0),
            context_fetch_time=random.uniform(0.1, 1.5),
            errors_count=0,
            warnings_count=random.randint(0, 1)
        )
        
        db.add(operation)
        
        # Generate realistic live operation logs
        live_logs = [
            ("INFO", f"Starting {command} operation for {repo}", "pr_agent.core", "handle_request"),
            ("DEBUG", f"Operation ID: {operation_id}, Request ID: {operation.request_id}", "pr_agent.core", "handle_request"),
            ("INFO", f"Authenticating with GitHub for repository {repo}", "pr_agent.git_provider", "authenticate"),
            ("INFO", f"Fetching PR data from {operation.pr_url}", "pr_agent.git_provider", "get_pr_data"),
            ("DEBUG", f"Retrieved PR metadata: title, body, and file list", "pr_agent.git_provider", "get_pr_data"),
            ("INFO", f"Beginning {command} analysis", f"pr_agent.tools.{command}er", "analyze_pr")
        ]
        
        # Add command-specific in-progress logs
        if command == "review":
            live_logs.extend([
                ("DEBUG", "Extracting diff hunks and file modifications", "pr_agent.algo.git_processing", "process_diff"),
                ("INFO", "Running static code analysis", "pr_agent.tools.reviewer", "static_analysis"),
                ("DEBUG", f"Found {random.randint(5, 15)} files to review", "pr_agent.tools.reviewer", "count_files")
            ])
        elif command == "describe":
            live_logs.extend([
                ("DEBUG", "Extracting commit messages and change patterns", "pr_agent.algo.git_processing", "analyze_commits"),
                ("INFO", "Detecting PR type and scope", "pr_agent.tools.describer", "detect_pr_type")
            ])
        elif command == "improve":
            live_logs.extend([
                ("DEBUG", "Running linting and style analysis", "pr_agent.tools.improver", "run_linters"),
                ("INFO", "Analyzing code for improvement opportunities", "pr_agent.tools.improver", "analyze_code")
            ])
        
        # Create linked logs
        for i, (level, message, module, function) in enumerate(live_logs):
            log_time = operation.started_at + timedelta(seconds=i * random.randint(3, 8))
            
            log_entry = LogEntryDB(
                timestamp=log_time,
                level=level,
                message=message,
                module=module,
                function=function,
                line=random.randint(50, 300),
                pr_url=operation.pr_url,
                command=operation.command,
                installation_id=operation.installation_id,
                repo=operation.repo,
                sender=operation.sender,
                request_id=operation.request_id,
                status=operation.status,
                analytics=True,
                app_name="pr-agent",
                git_provider="github"
            )
            
            db.add(log_entry)
        
        db.commit()
        db.close()
        
        return {
            "status": "success",
            "message": f"Simulated live {command} activity for operation {operation_id} with {len(live_logs)} linked logs",
            "operation_id": operation_id
        }
        
    except Exception as e:
        return {"status": "error", "message": f"Failed to simulate activity: {str(e)}"}


async def trigger_test_error() -> Dict[str, Any]:
    """Create a test operation that ends in error"""
    try:
        db = SessionLocal()
        
        operation_id = f"error-op-{uuid.uuid4().hex[:8]}"
        
        operation = OperationDB(
            operation_id=operation_id,
            command="improve",
            repo="error/test-repo",
            pr_url=f"https://github.com/error/test-repo/pull/{random.randint(1, 20)}",
            status="failed",
            started_at=datetime.utcnow() - timedelta(minutes=2),
            last_updated=datetime.utcnow(),
            completed_at=datetime.utcnow(),
            duration=120.5,
            error_details="Simulated API timeout error for testing",
            installation_id=f"err_{random.randint(10000, 99999)}",
            sender="error-test-user",
            request_id=f"err_{uuid.uuid4().hex[:12]}",
            response_time=5.2,
            context_fetch_time=1.1,
            ai_processing_time=15.8,
            errors_count=1,
            warnings_count=2
        )
        
        db.add(operation)
        db.commit()
        db.close()
        
        return {
            "status": "success",
            "message": f"Created test error operation {operation_id}",
            "operation_id": operation_id
        }
        
    except Exception as e:
        return {"status": "error", "message": f"Failed to create error test: {str(e)}"}


async def fail_live_activity(operation_id: str) -> Dict[str, Any]:
    """Fail a live activity operation"""
    try:
        db = SessionLocal()
        
        # Find the operation
        operation = db.query(OperationDB).filter(OperationDB.operation_id == operation_id).first()
        if not operation:
            return {"status": "error", "message": f"Operation {operation_id} not found"}
        
        # Update to failed status
        operation.status = "failed"
        operation.completed_at = datetime.utcnow()
        operation.last_updated = datetime.utcnow()
        operation.error_details = "Manually failed via developer tools"
        
        if operation.started_at:
            duration = (operation.completed_at - operation.started_at).total_seconds()
            operation.duration = duration
        
        db.commit()
        db.close()
        
        return {
            "status": "success",
            "message": f"Operation {operation_id} marked as failed"
        }
        
    except Exception as e:
        return {"status": "error", "message": f"Failed to fail activity: {str(e)}"}


async def succeed_live_activity(operation_id: str) -> Dict[str, Any]:
    """Succeed a live activity operation"""
    try:
        db = SessionLocal()
        
        # Find the operation
        operation = db.query(OperationDB).filter(OperationDB.operation_id == operation_id).first()
        if not operation:
            return {"status": "error", "message": f"Operation {operation_id} not found"}
        
        # Update to completed status
        operation.status = "completed"
        operation.completed_at = datetime.utcnow()
        operation.last_updated = datetime.utcnow()
        operation.suggestions_count = random.randint(3, 8)
        operation.error_details = None
        
        if operation.started_at:
            duration = (operation.completed_at - operation.started_at).total_seconds()
            operation.duration = duration
        
        db.commit()
        db.close()
        
        return {
            "status": "success",
            "message": f"Operation {operation_id} marked as completed"
        }
        
    except Exception as e:
        return {"status": "error", "message": f"Failed to succeed activity: {str(e)}"}


async def clear_all_data() -> Dict[str, Any]:
    """Clear all test and development data"""
    try:
        db = SessionLocal()
        
        operations_count = db.query(OperationDB).count()
        logs_count = db.query(LogEntryDB).count()
        
        db.query(LogEntryDB).delete()
        db.query(OperationDB).delete()
        
        db.commit()
        db.close()
        
        return {
            "status": "success",
            "message": f"Cleared {operations_count} operations and {logs_count} logs"
        }
        
    except Exception as e:
        return {"status": "error", "message": f"Failed to clear data: {str(e)}"} 