# PR-Agent Dashboard Integration Guide

This guide explains how to integrate your AI dashboard with the pr-agent logging system to monitor operations in real-time.

## Overview

The pr-agent has a sophisticated logging system built on **Loguru** that you can hook into for dashboard monitoring. The system provides several integration points for capturing:

- **Status Updates**: Running states like "processing PR", "self reflecting", "generating suggestions"
- **Context Information**: Which PR, command, step progress, user details
- **Error Tracking**: Detailed error information with stack traces and artifacts
- **Full Logs**: Complete audit trail of all operations

## Integration Approaches

### 1. Custom Loguru Sink (Recommended)

The cleanest approach is to use a custom Loguru sink that captures all logs and sends them to your dashboard.

#### Implementation

The `pr_agent/log/dashboard_sink.py` file provides a complete implementation:

```python
from pr_agent.log.dashboard_sink import setup_dashboard_sink

# Setup the dashboard sink
dashboard_sink = setup_dashboard_sink(
    dashboard_url="https://your-dashboard.com/api",
    api_key="your-api-key"
)
```

#### Configuration

Add these settings to your `configuration.toml`:

```toml
[dashboard]
url = "https://your-dashboard.com/api"
api_key = "your-secret-key"
enabled = true
batch_size = 10
flush_interval = 5.0
```

#### Data Format

The sink sends structured JSON data to your dashboard:

```json
{
    "timestamp": "2024-01-15T10:30:00Z",
    "level": "INFO",
    "message": "Processing PR review",
    "status": "processing_pr",
    "pr_url": "https://github.com/org/repo/pull/123",
    "command": "review",
    "operation_id": "uuid-1234",
    "sender": "username",
    "repo": "org/repo",
    "request_id": "req-5678",
    "artifact": {
        "additional_data": "..."
    }
}
```

### 2. Existing Analytics System

Leverage the built-in analytics filtering system:

```python
# This log will be captured by analytics filter
get_logger().info("PR operation completed", 
                  analytics=True, 
                  pr_statistics=stats_data)
```

### 3. Context-Aware Logging

Use the existing contextualize feature:

```python
with get_logger().contextualize(
    operation_id="op-123",
    status="processing_pr",
    pr_url=pr_url,
    command="review"
):
    # All logs within this context will include the context data
    get_logger().info("Starting PR analysis")
    # ... processing ...
    get_logger().info("PR analysis completed")
```

## Dashboard API Endpoints

The `pr_agent/servers/dashboard_api.py` provides endpoints your dashboard can query:

### Status Overview
```
GET /api/v1/dashboard/status
```
Returns active operations and system stats.

### Operation Details  
```
GET /api/v1/dashboard/operations?limit=50&include_completed=true
```
Returns active and completed operations.

### Specific Operation
```
GET /api/v1/dashboard/operation/{operation_id}
```
Returns details of a specific operation.

### Logs Query
```
GET /api/v1/dashboard/logs?level=ERROR&pr_url=...&limit=100
```
Query logs with filters.

### Log Reception
```
POST /api/v1/dashboard/logs/immediate  # For real-time logs
POST /api/v1/dashboard/logs/batch      # For batch logs
```

## Status Tracking

The system can track detailed operation states:

### Operation States
- `starting` - Operation initialized
- `fetching_context` - Loading PR data and context
- `processing_pr` - Main processing (review, describe, etc.)
- `generating_suggestions` - AI generating code suggestions
- `self_reflecting` - AI validating/improving suggestions
- `publishing` - Publishing results to PR
- `completed` - Operation successful
- `failed` - Operation failed
- `cancelled` - Operation cancelled

### Usage Example

```python
from pr_agent.log.status_tracker import (
    start_pr_operation, 
    update_pr_operation_status,
    OperationType, 
    OperationStatus
)

# Start tracking
operation_id = await start_pr_operation(
    pr_url="https://github.com/org/repo/pull/123",
    operation_type=OperationType.REVIEW,
    sender="username",
    repo="org/repo"
)

# Update status
await update_pr_operation_status(
    operation_id, 
    OperationStatus.PROCESSING_PR,
    step="Analyzing code changes",
    step_number=2,
    total_steps=5
)

# Complete
await complete_pr_operation(operation_id, "Review completed successfully")
```

## Configuration Options

### Environment Variables
```bash
LOG_LEVEL=DEBUG
DASHBOARD_URL=https://your-dashboard.com/api
DASHBOARD_API_KEY=your-secret-key
```

### Configuration File
```toml
[config]
log_level = "DEBUG"
verbosity_level = 2

[dashboard]
url = "https://your-dashboard.com/api"
api_key = "your-secret-key"
enabled = true
batch_size = 10
flush_interval = 5.0
api_port = 8001
```

## Real-time Updates

For real-time dashboard updates, the dashboard sink supports:

1. **Immediate dispatch** for errors and status changes
2. **Batch dispatch** for regular logs
3. **WebSocket support** (implement in your dashboard backend)
4. **Server-Sent Events** for live updates

## Example Dashboard Implementation

### Backend (FastAPI/Django/Flask)

```python
@app.post("/api/logs/immediate")
async def receive_immediate_log(log_data: dict):
    # Store in database
    await store_log(log_data)
    
    # Trigger real-time update
    if log_data.get("status"):
        await broadcast_status_update(log_data)
    
    if log_data.get("level") in ["ERROR", "CRITICAL"]:
        await notify_error(log_data)
    
    return {"status": "received"}
```

### Frontend (React/Vue/Angular)

```javascript
// Real-time status updates
const eventSource = new EventSource('/api/dashboard/stream');
eventSource.onmessage = (event) => {
    const data = JSON.parse(event.data);
    updateDashboard(data);
};

// Query operations
const operations = await fetch('/api/v1/dashboard/operations')
    .then(r => r.json());
```

## Security Considerations

1. **API Key Authentication**: Use secure API keys for dashboard communication
2. **Rate Limiting**: Implement rate limiting on dashboard endpoints
3. **Data Sanitization**: Sanitize log data before storing/displaying
4. **Access Control**: Restrict dashboard access to authorized users
5. **HTTPS Only**: Use HTTPS for all dashboard communications

## Monitoring Metrics

Track these key metrics in your dashboard:

### Operational Metrics
- Active operations count
- Average processing time
- Success/failure rates
- Operations per hour/day

### Performance Metrics  
- Memory usage during operations
- AI API call latency
- Token usage and costs
- Error rates by operation type

### System Health
- Log volume and growth
- Disk space usage
- API endpoint response times
- Background task queue health

## Troubleshooting

### Common Issues

1. **Logs not appearing**: Check dashboard URL and API key configuration
2. **Missing status updates**: Ensure status tracking is enabled
3. **High memory usage**: Adjust batch size and flush interval
4. **Network timeouts**: Configure appropriate timeout values

### Debug Mode

Enable verbose logging for troubleshooting:

```toml
[config]
log_level = "DEBUG"
verbosity_level = 2
```

### Health Checks

Monitor these endpoints for system health:
- `/api/v1/dashboard/health` - Dashboard API health
- Check log volume and error rates
- Monitor active operation counts

## Dependencies

For full functionality, you may need these additional packages:

```bash
pip install aiohttp fastapi uvicorn
```

These are optional and only needed if you use the dashboard sink or API endpoints.

## Example Integration

Here's a complete example of integrating the dashboard with a FastAPI app:

```python
from fastapi import FastAPI
from pr_agent.servers.dashboard_api import router as dashboard_router
from pr_agent.log.dashboard_sink import setup_dashboard_sink

app = FastAPI()

# Setup dashboard sink
setup_dashboard_sink()

# Include dashboard routes
app.include_router(dashboard_router, prefix="/api/v1")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

This gives you a complete monitoring solution for your AI dashboard with real-time status updates, error tracking, and comprehensive logging capabilities. 