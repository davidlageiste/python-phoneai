az webapp config set \
  --resource-group LyraeTalk \
  --name LyraeAPI \
  --startup-file "gunicorn --bind=0.0.0.0 app:app"