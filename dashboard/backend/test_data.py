"""
Test Data Generation Module for Developer Tools
"""
import random
import uuid
from datetime import datetime, timedelta
from typing import Dict, Any
from database import SessionLocal
from models import JobDB, OperationDB, LogEntryDB


def _get_realistic_error(command: str) -> str:
    """Generate realistic error messages based on command type"""
    error_templates = {
        "job": [
            "Job execution failed: multiple operations encountered errors",
            "Job cancelled due to resource constraints",
            "Job timeout: exceeded maximum execution time of 30 minutes",
            "Job failed: GitHub API rate limit exceeded",
            "Job terminated: insufficient permissions for repository access"
        ],
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
    logs.append(("INFO", f"Starting {command} operation for {operation.repository}", "pr_agent.core", "handle_request"))
    logs.append(("DEBUG", f"Operation ID: {operation.operation_id}, Request ID: {operation.request_id}", "pr_agent.core", "handle_request"))
    
    # Authentication and setup
    logs.append(("INFO", f"Authenticating with GitHub for repository {operation.repository}", "pr_agent.git_provider", "authenticate"))
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
    """Generate sample jobs, operations and logs for testing"""
    db = None
    try:
        db = SessionLocal()
        
        jobs_created = 0
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
        
        job_types = [
            {"type": "webhook", "weight": 5},
            {"type": "cli", "weight": 2},
            {"type": "manual", "weight": 2},  
            {"type": "api", "weight": 1}
        ]
        
        job_status_scenarios = [
            {"status": "completed", "weight": 4},
            {"status": "failed", "weight": 3},
            {"status": "running", "weight": 2},
            {"status": "cancelled", "weight": 1}
        ]
        
        operation_status_scenarios = [
            {"status": "completed", "weight": 6},
            {"status": "failed", "weight": 2},
            {"status": "processing", "weight": 1},
            {"status": "fetching_context", "weight": 1},
            {"status": "self_reflecting", "weight": 1},
            {"status": "publishing", "weight": 1}
        ]
        
        # Generate 15 jobs, each with 1-3 operations
        for i in range(15):
            job_id = f"job-{uuid.uuid4().hex[:8]}"
            
            # Weighted random selection for job first to determine timing
            repo = random.choice(test_repos)
            job_type = random.choices(
                [jt["type"] for jt in job_types],
                weights=[jt["weight"] for jt in job_types]
            )[0]
            job_status = random.choices(
                [s["status"] for s in job_status_scenarios],
                weights=[s["weight"] for s in job_status_scenarios]
            )[0]
            
            # Set start time based on status - running jobs should be more recent
            if job_status == "running":
                started_time = datetime.utcnow() - timedelta(
                    minutes=random.randint(1, 60)  # Running jobs: 1-60 minutes ago
                )
            elif job_status == "failed":
                started_time = datetime.utcnow() - timedelta(
                    minutes=random.randint(10, 720)  # Failed jobs: 10 minutes to 12 hours ago
                )
            else:  # completed, cancelled
                started_time = datetime.utcnow() - timedelta(
                    minutes=random.randint(30, 2880)  # Other jobs: 30 minutes to 2 days ago
                )
            sender = random.choice(test_senders)
            request_id = f"req_{uuid.uuid4().hex[:12]}"
            
            # Create job
            job = JobDB(
                job_id=job_id,
                job_type=job_type,
                source=f"{job_type}_trigger",
                status=job_status,
                repository=repo,
                pr_url=f"https://github.com/{repo}/pull/{random.randint(1000, 9999)}",
                trigger_user=sender,
                trigger_event="pull_request" if job_type == "webhook" else job_type,
                installation_id=f"inst_{random.randint(100000, 999999)}" if job_type == "webhook" else None,
                request_id=request_id,
                started_at=started_time,
                completed_at=datetime.utcnow() if job_status in ["completed", "failed", "cancelled"] else None,
                duration=random.uniform(30, 600) if job_status in ["completed", "failed", "cancelled"] else None,
                webhook_payload={"action": "opened", "number": random.randint(1000, 9999)} if job_type == "webhook" else None,
                result_summary={"message": f"Job completed with {random.randint(1, 3)} operations", "success": True} if job_status == "completed" else None,
                error_details=_get_realistic_error("job") if job_status == "failed" else None
            )
            
            db.add(job)
            jobs_created += 1
            
            # Generate 1-3 operations for this job
            num_operations = random.randint(1, 3)
            job_operations = []
            
            for j in range(num_operations):
                operation_id = f"op-{uuid.uuid4().hex[:8]}"
                op_started_time = started_time + timedelta(seconds=j * random.randint(5, 30))
                
                command = random.choices(
                    [cmd["cmd"] for cmd in test_commands],
                    weights=[cmd["weight"] for cmd in test_commands]
                )[0]
                
                # Operation status should be consistent with job status
                if job_status == "failed":
                    # Failed jobs: some operations completed, last one(s) failed
                    if j == num_operations - 1:
                        op_status = "failed"
                    else:
                        op_status = random.choice(["completed", "failed"])
                elif job_status == "running":
                    # Running jobs: earlier operations completed, later ones in progress
                    if j < num_operations - 1:
                        op_status = "completed"
                    else:
                        op_status = random.choice(["processing", "fetching_context", "self_reflecting", "publishing"])
                elif job_status == "cancelled":
                    # Cancelled jobs: some completed, some skipped
                    op_status = random.choice(["completed", "skipped"])
                else:  # completed
                    # Completed jobs: all operations completed (with occasional failures that were recovered)
                    op_status = random.choices(
                        ["completed", "failed"],
                        weights=[9, 1]  # 90% completed, 10% failed (but job still completed overall)
                    )[0]
                
                # Generate AI/LLM metrics for completed operations
                ai_models = [
                    "anthropic/claude-opus-4-6-20260205", "anthropic/claude-sonnet-4-6-20260205", "anthropic/claude-haiku-4-5-20251001",
                    "gemini/gemini-3.1-pro-preview", "gemini/gemini-3-flash-preview",
                    "gpt-5", "gpt-5-mini", "gpt-5.3-codex", "gpt-5.3-codex-spark"
                ]
                
                model_used = None
                input_tokens = None
                output_tokens = None
                estimated_dev_hours = None
                
                if op_status in ["completed", "failed"] and random.random() < 0.8:  # 80% of completed/failed ops have metrics
                    model_used = random.choice(ai_models)
                    
                    # Generate realistic token counts based on operation type
                    if command == "review":
                        input_tokens = random.randint(2000, 15000)
                        output_tokens = random.randint(500, 3000)
                        estimated_dev_hours = random.uniform(0.5, 4.0)
                    elif command == "describe":
                        input_tokens = random.randint(1000, 8000)
                        output_tokens = random.randint(200, 1000)
                        estimated_dev_hours = random.uniform(0.2, 1.5)
                    elif command == "improve":
                        input_tokens = random.randint(1500, 12000)
                        output_tokens = random.randint(300, 2000)
                        estimated_dev_hours = random.uniform(0.3, 3.0)
                    elif command == "test":
                        input_tokens = random.randint(2000, 10000)
                        output_tokens = random.randint(800, 4000)
                        estimated_dev_hours = random.uniform(1.0, 6.0)
                    elif command == "add_docs":
                        input_tokens = random.randint(1000, 6000)
                        output_tokens = random.randint(400, 2000)
                        estimated_dev_hours = random.uniform(0.5, 2.0)
                    else:  # update_changelog
                        input_tokens = random.randint(500, 3000)
                        output_tokens = random.randint(100, 800)
                        estimated_dev_hours = random.uniform(0.1, 0.8)

                operation = OperationDB(
                    operation_id=operation_id,
                    job_id=job_id,
                    operation_type=command,
                    command=command,
                    repository=repo,
                    pr_url=job.pr_url,
                    status=op_status,
                    started_at=op_started_time,
                    last_updated=datetime.utcnow(),
                    completed_at=datetime.utcnow() if op_status in ["completed", "failed", "skipped"] else None,
                    duration=random.uniform(15, 300) if op_status in ["completed", "failed", "skipped"] else None,
                    error_details=_get_realistic_error(command) if op_status == "failed" else None,
                    installation_id=job.installation_id,
                    sender=sender,
                    request_id=request_id,
                    response_time=random.uniform(0.3, 8.0) if op_status in ["completed", "failed"] else None,
                    context_fetch_time=random.uniform(0.1, 3.0) if op_status in ["completed", "failed"] else None,
                    ai_processing_time=random.uniform(3.0, 45.0) if op_status in ["completed", "failed"] else None,
                    # NEW: AI/LLM Metrics
                    model_used=model_used,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    estimated_dev_hours_saved=estimated_dev_hours,
                    suggestions_count=random.randint(2, 15) if op_status == "completed" and command in ["review", "improve"] else None,
                    errors_count=random.randint(0, 2),
                    warnings_count=random.randint(0, 4),
                    result_data={"suggestions": random.randint(1, 8)} if op_status == "completed" else None
                )
                
                db.add(operation)
                operations_created += 1
                job_operations.append(operation)
            
            # Generate realistic linked logs for each operation in this job
            for operation in job_operations:
                log_messages = _generate_realistic_log_sequence(operation)
                
                for k, (level, message, module, function) in enumerate(log_messages):
                    log_time = operation.started_at + timedelta(seconds=k * random.randint(2, 15))
                    
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
                        repository=operation.repository,
                        sender=operation.sender,
                        request_id=operation.request_id,
                        status=operation.status,
                        analytics=random.choice([True, False]),
                        app_name="pr-agent",
                        git_provider="github",
                        job_id=job_id,
                        operation_id=operation.operation_id
                    )
                    
                    db.add(log_entry)
                    logs_created += 1
            
        # Update job counts after all operations and logs are created
        # Move this outside the job creation loop to update ALL jobs after everything is created
        for job in db.query(JobDB).all():
            # Count operations for this job
            operations_count = db.query(OperationDB).filter(OperationDB.job_id == job.job_id).count()
            job.operations_count = operations_count
            
            # Count completed and failed operations
            completed_operations = db.query(OperationDB).filter(
                OperationDB.job_id == job.job_id,
                OperationDB.status == "completed"
            ).count()
            job.completed_operations = completed_operations
            
            failed_operations = db.query(OperationDB).filter(
                OperationDB.job_id == job.job_id,
                OperationDB.status == "failed"
            ).count()
            job.failed_operations = failed_operations
            
            # Count logs for this job
            total_logs = db.query(LogEntryDB).filter(LogEntryDB.job_id == job.job_id).count()
            job.total_logs = total_logs
            
            # Count error and warning logs
            error_count = db.query(LogEntryDB).filter(
                LogEntryDB.job_id == job.job_id,
                LogEntryDB.level.in_(['ERROR', 'CRITICAL'])
            ).count()
            job.error_count = error_count
            
            warning_count = db.query(LogEntryDB).filter(
                LogEntryDB.job_id == job.job_id,
                LogEntryDB.level == 'WARNING'
            ).count()
            job.warning_count = warning_count
        
        db.commit()
        db.close()
        
        return {
            "status": "success",
            "message": f"Generated {jobs_created} test jobs, {operations_created} test operations and {logs_created} test logs with realistic job/operation hierarchy",
            "data": {"jobs": jobs_created, "operations": operations_created, "logs": logs_created}
        }
        
    except Exception as e:
        if db:
            db.rollback()
            db.close()
        return {"status": "error", "message": f"Failed to generate test data: {str(e)}"}


async def simulate_live_activity() -> Dict[str, Any]:
    """Simulate a live job with operations in progress with linked logs"""
    try:
        db = SessionLocal()
        
        job_id = f"live-job-{uuid.uuid4().hex[:8]}"
        operation_id = f"live-op-{uuid.uuid4().hex[:8]}"
        demo_repos = ["microsoft/vscode", "facebook/react", "nodejs/node"]
        demo_commands = ["review", "describe", "improve"]
        demo_users = ["alice-dev", "bob-maintainer", "carol-contributor"]
        
        repo = random.choice(demo_repos)
        command = random.choice(demo_commands)
        user = random.choice(demo_users)
        request_id = f"live_{uuid.uuid4().hex[:12]}"
        started_time = datetime.utcnow() - timedelta(seconds=random.randint(15, 120))
        
        # Create live job
        job = JobDB(
            job_id=job_id,
            job_type="webhook",
            source="webhook_trigger",
            status="running",
            repository=repo,
            pr_url=f"https://github.com/{repo}/pull/{random.randint(1000, 5000)}",
            trigger_user=user,
            trigger_event="pull_request",
            installation_id=f"live_{random.randint(100000, 999999)}",
            request_id=request_id,
            started_at=started_time,
            webhook_payload={"action": "opened", "number": random.randint(1000, 5000)}
        )
        
        db.add(job)
        
        # Create live operation
        operation = OperationDB(
            operation_id=operation_id,
            job_id=job_id,
            operation_type=command,
            command=command,
            repository=repo,
            pr_url=job.pr_url,
            status="processing",
            started_at=started_time,
            last_updated=datetime.utcnow(),
            installation_id=job.installation_id,
            sender=user,
            request_id=request_id,
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
                repository=operation.repository,
                sender=operation.sender,
                request_id=operation.request_id,
                status=operation.status,
                analytics=True,
                app_name="pr-agent",
                git_provider="github",
                job_id=job_id,
                operation_id=operation_id
            )
            
            db.add(log_entry)
        
        db.commit()
        db.close()
        
        return {
            "status": "success",
            "message": f"Simulated live {command} activity for job {job_id} with operation {operation_id} and {len(live_logs)} linked logs",
            "job_id": job_id,
            "operation_id": operation_id
        }
        
    except Exception as e:
        return {"status": "error", "message": f"Failed to simulate activity: {str(e)}"}


async def trigger_test_error() -> Dict[str, Any]:
    """Create a test job and operation that ends in error"""
    try:
        db = SessionLocal()
        
        job_id = f"error-job-{uuid.uuid4().hex[:8]}"
        operation_id = f"error-op-{uuid.uuid4().hex[:8]}"
        request_id = f"err_{uuid.uuid4().hex[:12]}"
        
        # Create failed job
        job = JobDB(
            job_id=job_id,
            job_type="manual",
            source="manual_trigger",
            status="failed",
            repository="error/test-repo",
            pr_url=f"https://github.com/error/test-repo/pull/{random.randint(1, 20)}",
            trigger_user="error-test-user",
            trigger_event="manual",
            request_id=request_id,
            started_at=datetime.utcnow() - timedelta(minutes=2),
            completed_at=datetime.utcnow(),
            duration=120.5,
            error_details="Simulated job failure for testing"
        )
        
        db.add(job)
        
        # Create failed operation
        operation = OperationDB(
            operation_id=operation_id,
            job_id=job_id,
            operation_type="improve",
            command="improve",
            repository="error/test-repo",
            pr_url=job.pr_url,
            status="failed",
            started_at=datetime.utcnow() - timedelta(minutes=2),
            last_updated=datetime.utcnow(),
            completed_at=datetime.utcnow(),
            duration=120.5,
            error_details="Simulated API timeout error for testing",
            installation_id=f"err_{random.randint(10000, 99999)}",
            sender="error-test-user",
            request_id=request_id,
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
            "message": f"Created test error job {job_id} with operation {operation_id}",
            "job_id": job_id,
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
        from models import NotificationEventDB, HealthCacheDB, MetricsAggregateDB
        
        db = SessionLocal()
        
        # Count records before deletion
        jobs_count = db.query(JobDB).count()
        operations_count = db.query(OperationDB).count()  
        logs_count = db.query(LogEntryDB).count()
        notification_events_count = db.query(NotificationEventDB).count()
        health_cache_count = db.query(HealthCacheDB).count()
        metrics_aggregate_count = db.query(MetricsAggregateDB).count()
        
        # Delete in order due to foreign key constraints
        db.query(LogEntryDB).delete()
        db.query(OperationDB).delete()
        db.query(JobDB).delete()
        db.query(NotificationEventDB).delete()
        db.query(HealthCacheDB).delete()
        db.query(MetricsAggregateDB).delete()
        
        db.commit()
        db.close()
        
        total_cleared = jobs_count + operations_count + logs_count + notification_events_count + health_cache_count + metrics_aggregate_count
        
        return {
            "status": "success",
            "message": f"Cleared {jobs_count} jobs, {operations_count} operations, {logs_count} logs, {notification_events_count} notification events, {health_cache_count} health cache entries, and {metrics_aggregate_count} metrics aggregates ({total_cleared} total records)"
        }
        
    except Exception as e:
        return {"status": "error", "message": f"Failed to clear data: {str(e)}"}


async def generate_ai_metrics_data() -> Dict[str, Any]:
    """Generate sample operations with AI metrics data for testing"""
    try:
        db = SessionLocal()
        
        # AI models with realistic usage patterns
        ai_models = [
            {"name": "anthropic/claude-opus-4-6-20260205", "weight": 3, "input_range": (2800, 11000), "output_range": (700, 2800), "dev_hours": (0.9, 4.2)},
            {"name": "anthropic/claude-sonnet-4-6-20260205", "weight": 5, "input_range": (2500, 10000), "output_range": (600, 2500), "dev_hours": (0.7, 3.5)},
            {"name": "anthropic/claude-haiku-4-5-20251001", "weight": 2, "input_range": (1500, 6000), "output_range": (300, 1500), "dev_hours": (0.3, 2.0)},
            {"name": "gpt-5.3-codex", "weight": 4, "input_range": (3000, 12000), "output_range": (800, 3000), "dev_hours": (0.8, 4.0)},
            {"name": "gpt-5.3-codex-spark", "weight": 3, "input_range": (2000, 8000), "output_range": (500, 2000), "dev_hours": (0.5, 3.0)},
            {"name": "gemini/gemini-3.1-pro-preview", "weight": 4, "input_range": (2200, 9000), "output_range": (550, 2200), "dev_hours": (0.6, 3.2)},
        ]
        
        commands = ["review", "describe", "improve", "test", "add_docs", "update_changelog"]
        repos = ["microsoft/vscode", "facebook/react", "google/tensorflow", "vercel/next.js", "nodejs/node"]
        
        operations_created = 0
        
        # Generate 50 operations with AI metrics
        for i in range(50):
            # Select model based on weights
            model_choices = []
            for model in ai_models:
                model_choices.extend([model] * model["weight"])
            selected_model = random.choice(model_choices)
            
            # Generate realistic metrics
            input_tokens = random.randint(*selected_model["input_range"])
            output_tokens = random.randint(*selected_model["output_range"])
            dev_hours = round(random.uniform(*selected_model["dev_hours"]), 2)
            
            # Create job
            job_id = f"ai-job-{uuid.uuid4().hex[:8]}"
            operation_id = f"ai-op-{uuid.uuid4().hex[:8]}"
            
            start_time = datetime.utcnow() - timedelta(days=random.randint(0, 30), hours=random.randint(0, 23))
            duration = random.uniform(30, 300)  # 30 seconds to 5 minutes
            
            job = JobDB(
                job_id=job_id,
                job_type=random.choice(["webhook", "api", "cli"]),
                source="github",
                status="completed",
                repository=random.choice(repos),
                pr_url=f"https://github.com/{random.choice(repos)}/pull/{random.randint(1, 500)}",
                trigger_user=f"user-{random.randint(1, 20)}",
                trigger_event="pull_request",
                started_at=start_time,
                completed_at=start_time + timedelta(seconds=duration),
                duration=duration,
                operations_count=1,
                completed_operations=1,
                request_id=f"req_{uuid.uuid4().hex[:12]}"
            )
            
            db.add(job)
            
            # Create operation with AI metrics
            operation = OperationDB(
                operation_id=operation_id,
                job_id=job_id,
                operation_type=random.choice(commands),
                command=random.choice(commands),
                status="completed",
                repository=job.repository,
                pr_url=job.pr_url,
                installation_id=f"inst_{random.randint(10000, 99999)}",
                sender=job.trigger_user,
                request_id=job.request_id,
                started_at=start_time,
                last_updated=start_time + timedelta(seconds=duration),
                completed_at=start_time + timedelta(seconds=duration),
                duration=duration,
                response_time=random.uniform(2.0, 15.0),
                context_fetch_time=random.uniform(0.5, 3.0),
                ai_processing_time=random.uniform(10.0, 60.0),
                
                # AI/LLM Metrics
                model_used=selected_model["name"],
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                estimated_dev_hours_saved=dev_hours,
                
                # Results
                suggestions_count=random.randint(1, 8) if random.choice(commands) in ["review", "improve"] else None,
                errors_count=random.randint(0, 2) if random.random() < 0.3 else 0,
                warnings_count=random.randint(0, 3) if random.random() < 0.4 else 0,
            )
            
            db.add(operation)
            operations_created += 1
        
        db.commit()
        db.close()
        
        return {
            "status": "success",
            "message": f"Generated {operations_created} operations with AI metrics data",
            "operations_created": operations_created
        }
        
    except Exception as e:
        return {"status": "error", "message": f"Failed to generate AI metrics data: {str(e)}"}