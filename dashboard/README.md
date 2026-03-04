# PR Agent Dashboard

A real-time monitoring dashboard for PR Agent operations, providing insights into:
- **Status tracking** (running PRs, fetching context, self-reflection, etc.)
- **Context monitoring** (which PR, step/command progress)
- **Error tracking** (issues that occurred)
- **Full logs** (for troubleshooting/auditing)
- **Performance metrics** (response times, success rates, context fetch performance)

## Architecture

- **Frontend**: React application with Tailwind CSS and Recharts
- **Backend**: FastAPI Python server with WebSocket support
- **Real-time updates**: WebSocket connections for live monitoring
- **Data storage**: In-memory storage (easily replaceable with PostgreSQL/MongoDB)

## Quick Start

### Backend Setup

```bash
cd dashboard/backend
pip install -r requirements.txt
python main.py
```

The API will be available at `http://localhost:8000`

### Frontend Setup

```bash
cd dashboard/frontend
npm install
npm start
```

The dashboard will be available at `http://localhost:3000`

### Run with Docker (local)

From the **repository root**, rebuild and run both containers:

```bash
python dashboard/run_docker_local.py
```

- Backend: `http://localhost:8000` (SQLite data in a Docker volume)
- Frontend: `http://localhost:3000`

Options: `--no-rebuild` to use existing images; `--stop` to stop and remove the containers.

## Features

### 📊 **Overview Dashboard**
- Real-time operation counts
- Recent activity feed
- System health indicators
- Performance metrics summary

### 🔍 **Operations Tracking**
- Live operation status updates
- Context fetching progress
- Operation duration tracking
- Filtering and sorting capabilities

### 📝 **Comprehensive Logging**
- Real-time log streaming
- Log level filtering
- Search functionality
- Detailed log inspection
- Export capabilities

### 📈 **Performance Metrics**
- Response time charts
- Success rate tracking
- Context fetch performance
- Operation type breakdown
- Historical trends

### 🔄 **Real-time Updates**
- WebSocket-based live updates
- Automatic dashboard refresh
- Status change notifications
- Error alerts

## Integration with PR Agent

The dashboard integrates with PR Agent through the enhanced logging sink in `pr_agent/log/dashboard_sink.py`. This sink:

1. **Captures all logs** automatically via Loguru
2. **Extracts status information** from log messages
3. **Sends real-time updates** to the dashboard
4. **Batches logs** for efficiency
5. **Handles errors gracefully** without affecting PR Agent operation

### Status Tracking

The dashboard tracks these operation statuses:
- `starting` - Operation initiated
- `fetching_context` - Retrieving code context
- `context_completed` - Context successfully fetched
- `context_disabled` - Context service disabled
- `context_failed` - Context fetching failed
- `preparing` - Preparing for processing
- `processing` - Main operation in progress
- `self_reflecting` - AI self-reflection phase
- `publishing` - Publishing results
- `completed` - Operation finished successfully
- `failed` - Operation failed
- `skipped` - Operation skipped

## Configuration

### Backend Configuration

Create a `.env` file in `dashboard/backend/`:

```env
API_HOST=0.0.0.0
API_PORT=8000
DEBUG=True
MAX_LOGS_STORAGE=10000
MAX_OPERATIONS_STORAGE=1000
ALLOWED_ORIGINS=http://localhost:3000
```

### Frontend Configuration

Set environment variables in `dashboard/frontend/.env`:

```env
REACT_APP_API_URL=http://localhost:8000
```

## API Endpoints

### Operations
- `GET /api/operations` - List operations
- `GET /api/operations/{id}` - Get operation details

### Logs
- `GET /api/logs` - List logs
- `GET /api/logs/operation/{id}` - Get logs for operation
- `POST /logs/immediate` - Receive immediate log
- `POST /logs/batch` - Receive batch logs

### Metrics
- `GET /api/metrics` - Get system metrics
- `GET /api/health` - Health check

### Real-time
- `WebSocket /ws` - Real-time updates

## Development

### Adding New Metrics

1. Update `models.py` with new metric fields
2. Modify the metrics calculation in `main.py`
3. Add visualization in the frontend `MetricsChart.js`

### Extending Status Tracking

1. Add new status patterns in `dashboard_sink.py`
2. Update the `OperationStatus` enum in `models.py`
3. Add status handling in frontend components

## Production Deployment

For production deployment:

1. **Replace in-memory storage** with PostgreSQL or MongoDB
2. **Add authentication** and authorization
3. **Configure HTTPS** and secure WebSocket connections
4. **Set up monitoring** and alerting
5. **Configure log retention** and cleanup policies

## Future Enhancements

- [ ] Database persistence (PostgreSQL/MongoDB)
- [ ] User authentication and authorization
- [ ] Alert system for errors and performance issues
- [ ] Historical data analysis and reporting
- [ ] Integration with external monitoring tools
- [ ] Custom dashboard widgets
- [ ] Export and reporting features
- [ ] Mobile-responsive design improvements 