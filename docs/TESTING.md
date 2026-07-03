# Testing TimeForge

TimeForge includes a comprehensive automated test suite to ensure the stability of models, views, and core scheduling algorithms.

## Running the Tests

To run the full test suite, simply use Django's test runner:

```bash
python manage.py test
```

This will automatically create a temporary test database, apply migrations, run all tests, and destroy the test database when finished. Your local development data will remain untouched.

### Running Specific Tests

To run tests for a specific app:
```bash
python manage.py test academics
python manage.py test timetable
```

To run a specific test case:
```bash
python manage.py test timetable.tests.TimetableIntegrationTests
```

## Test Coverage Expectations

The automated test suite covers the following areas:

1. **Models and Validation**: 
   - `core`: Ensures single-active-semester rules and room capacity constraints.
   - `academics`: Validates uniqueness of sections within a semester, subject properties, and teacher profiles.
   - `accounts`: Ensures custom `User` roles (`ADMIN`, `TEACHER`) are correctly enforced upon creation.
   - `scheduling`: Tests the constraints and algorithmic core logic (via `scheduling/tests/test_engine.py`).

2. **View Permissions**:
   - `scheduling`: Prevents unauthorized access to Admin-only configuration views.
   - `timetable`: Enforces strict Role-Based Access Control (RBAC) on the timetable generation endpoints, exports, drag-and-drop validation, and Admin-only grids.

3. **End-to-End Integration**:
   - The integration test simulates the entire lifecycle of a timetable:
     1. Seed minimal infrastructure and academic data.
     2. Run the generation algorithm.
     3. Verify the generated timetable is correctly displayed on the grid views.
     4. Use the drag-and-drop validation endpoint to securely move a slot.
     5. Export the resulting timetable to PDF and Excel, verifying correct MIME types.

## Manual QA Checklist

Some interactions are intentionally left out of the automated test suite and must be verified manually.

- [ ] **Drag-and-drop UI interaction**: Visually confirming that elements lock onto the grid correctly and that the visual feedback matches the status of the placement.
- [ ] **Cross-browser aesthetics**: Confirming that the PDF formatting and Excel column widths render beautifully in real viewers (Preview, Acrobat, Excel, Numbers) instead of just checking bytes.
- [ ] **Micro-animations**: Ensuring hover states and success/error toasts feel smooth and responsive in the browser.
