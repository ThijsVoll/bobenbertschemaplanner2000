# Refactored Tournament Scheduler

This package splits the original `app.py` into smaller, focused modules:

- `models.py`: data models (`Team`, `Match`)
- `constants.py`: static configuration and example data
- `browser.py`: browser / Pyodide bindings
- `state.py`: shared UI state
- `data_access.py`: JSON form and CSV input handling
- `scheduler.py`: scheduling and capacity algorithms
- `serializers.py`: result serialization and Excel row helpers
- `renderers.py`: UI rendering classes
- `exporters.py`: Excel export
- `controller.py`: app orchestration and event handling
- `app.py`: thin entry point


All modules are kept in a **flat layout** so the new `app.py` can stay the browser entry point without package-relative imports.
