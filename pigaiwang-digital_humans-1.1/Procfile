web: python -u main.py
worker: python -u -m taskiq worker app.tasks.broker:broker --workers 1
scheduler: python -u -m taskiq scheduler app.tasks.schedule:scheduler