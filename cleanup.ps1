Write-Host "🧹 Limpiando proyecto..."

# Scripts viejos
Remove-Item -Force index_pdfs.py, update_kb.py, rag_manager.py, setup.py -ErrorAction SilentlyContinue

# Archivos raros
Remove-Item -Force az, .prettierignore, prettier.config.js -ErrorAction SilentlyContinue

# Deployment antiguo
Remove-Item -Recurse -Force deploy_clean -ErrorAction SilentlyContinue
Remove-Item -Force deploy-*.zip -ErrorAction SilentlyContinue

# Config duplicada
Remove-Item -Force clientes_config.json -ErrorAction SilentlyContinue

# Cache Python
Remove-Item -Recurse -Force __pycache__ -ErrorAction SilentlyContinue
Get-ChildItem -Recurse -Directory -Filter "__pycache__" | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

# Data temporal
Remove-Item -Recurse -Force data -ErrorAction SilentlyContinue

# Índices duplicados
Remove-Item -Recurse -Force faiss_index -ErrorAction SilentlyContinue

Write-Host "✅ Limpieza completada"
Write-Host ""
Write-Host "📊 Archivos restantes:"

# Mostrar árbol (PowerShell no tiene 'tree -L 2')
tree /A /F
