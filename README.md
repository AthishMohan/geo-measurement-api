# Geospatial File Measurement API
A FastAPI application that accepts KML files and zipped Shapefiles, processes their geospatial features, calculates area and length measurements, and stores the results in SQLite.
## Features
- Upload KML files
- Upload zipped Shapefiles
- Validate file type and file size
- Store file information and measurements in SQLite
- Convert geographic coordinates to EPSG:4326
- Use UTM projection for area and length measurements
- Support Polygon, MultiPolygon, LineString, MultiLineString, Point, and MultiPoint geometries
- Handle missing CRS by assuming EPSG:4326 and adding a warning
- Protect against unsafe ZIP paths
- Provide measurement results through REST API endpoints
## How It Works
The application follows this flow:
Upload ? validate extension and size ? save file ? read geospatial data ? transform coordinates ? measure ? store results ? return response.
## API Endpoints
### Upload a file
POST /api/files/
Accepts:
- .kml
- .zip containing a Shapefile
### Get file information
GET /api/files/{file_id}/
Returns:
- filename
- processing status
- feature count
- CRS
- warnings
- errors
### Get measurements
GET /api/files/{file_id}/measurements/
Returns:
- total features
- measurement summary
- area in square metres
- area in hectares
- length in metres
- length in kilometres
- individual feature measurements
## CRS Handling
The API does not calculate area or length directly from latitude and longitude degrees.
Features are first converted to EPSG:4326 and then projected into the UTM zone based on the feature centroid. Measurements are then calculated using the projected geometry.
If a file does not contain a CRS, the application assumes EPSG:4326 and adds a warning.
## Architecture
The project is divided into three main parts:

- `app/main.py` - Handles HTTP requests, file uploads, validation, and API responses.
- `app/processing.py` - Reads geospatial files, handles CRS transformation, and calculates measurements.
- `app/db.py` - Handles SQLite database operations.

The API processes uploaded files synchronously. This keeps the implementation simple and makes the processing result available immediately after the upload request.
## Testing
The project includes automated tests for the main API functionality.

Run the tests with:

```powershell
python -m pytest
```

The test suite checks file upload, file information, measurements, and invalid file handling.
## Design Decisions

### Synchronous Processing
The API processes uploaded files during the upload request. This keeps the project simple and makes the result immediately available to the client.

### UTM Projection
Area and length are calculated using a projected UTM coordinate system instead of latitude and longitude degrees.

### SQLite
SQLite was selected because it is lightweight and easy to set up for this project. A production system with larger datasets could use PostgreSQL with PostGIS.

### Multiple Geometry Types
The application supports Polygon, MultiPolygon, LineString, MultiLineString, Point, and MultiPoint geometries.

### Missing CRS
When a file does not contain CRS information, EPSG:4326 is assumed and a warning is returned.

### ZIP Security
Uploaded ZIP files are checked to prevent unsafe paths such as path traversal during extraction.
## Limitations

- The API currently supports KML files and zipped Shapefiles.
- Processing is synchronous, so very large files may take longer to process.
- SQLite is suitable for this project but may not be ideal for a large production system.
- Measurements depend on the quality and CRS information of the uploaded geospatial data.
- The application uses UTM projection based on the feature centroid for measurements.
## What I Learned

This project helped me understand how to build a REST API with FastAPI, process geospatial data with GeoPandas and Shapely, handle coordinate reference systems with PyProj, store results using SQLite, write automated tests, and package an application with Docker.
## Future Improvements

- Add background processing for large files.
- Add PostgreSQL/PostGIS support for production-scale workloads.
- Add authentication and authorization.
- Add more geospatial file formats.
- Add stronger file-size and resource limits.
- Add more detailed API documentation and monitoring.
## Docker

Build the Docker image:

```powershell
docker build -t geo-measurement-api .
```

Run the container:

```powershell
docker run -p 8000:8000 geo-measurement-api
```

The API will then be available at http://127.0.0.1:8000.
## Git Workflow
- `git init`
- `git add .`
- `git commit -m "Initial project setup"`
- `git push -u origin main`
## Sample Files
- Add sample KML and zipped Shapefile files to the `samples/` directory for testing.
