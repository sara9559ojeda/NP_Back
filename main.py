"""Punto de entrada ASGI de Vercel. No ejecuta migraciones al arrancar."""
from app.main import create_app

app = create_app()
