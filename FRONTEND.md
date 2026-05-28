# Web Frontend for Indigo Analysis API

The API includes a web frontend hosted at the root path (`/`).

## Features

- **Analysis Discovery**: Browse all available analyses registered in the system
- **Dynamic Form Generation**: Automatically generates input forms based on analysis parameters
- **Real-time Results**: Submits jobs to the queue and polls for results
- **Result History**: Tracks all submitted jobs and their results (stored in browser's localStorage)
- **Type-Aware Inputs**: Automatically converts form inputs to appropriate types (int, float, bool, list)
- **Beautiful UI**: Modern gradient design with smooth animations and transitions

## Accessing the Frontend 

Once the API server is running:

```bash
heliotrapi serve
```

Open your browser and navigate to:
```
http://localhost:8000
```

## How to Use

1. **Select an Analysis**: Click on any analysis in the left panel to select it
2. **Fill in Parameters**: The form on the right will dynamically populate with the analysis parameters
3. **Submit**: Click "Submit Analysis" to queue the job
4. **View Results**: Results appear in the bottom panel and update in real-time
5. **Track History**: All submitted jobs are displayed with their status and results


### Frontend Files

- **`ui/index.html`** - Main HTML template
- **`ui/app.js`** - API client and UI logic
- **`ui/style.css`** - Responsive styling with gradient design

### Backend Integration

The frontend communicates with the following API endpoints:

- `GET /get_analyses` - Fetch list of available analyses with parameters
- `POST /analyse` - Submit a new analysis job
- `GET /result/latest` - Get the most recent result
- `GET /result/id/{request_id}` - Get result by request ID
- `GET /healthz` - Check API availability
- `GET /endpoints` - Get all available endpoints


## Example Workflow

1. Server starts with analyses registered (e.g., "double", "sum_numbers")
2. User opens frontend at http://localhost:8000
3. User selects "double" analysis from the list
4. Form shows parameter "number" with type hint
5. User enters "5" and clicks "Submit Analysis"
6. Request ID is displayed in a success message
7. Results panel shows the job with "running" status
8. Frontend polls for updates every 2 seconds
9. When complete, status changes and result is displayed
10. History is persisted automatically
