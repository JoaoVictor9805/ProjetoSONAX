python -m venv venv

.\venv\Scripts\Activate.ps1 -> Powershell
venv\Scripts\activate -> CMD
source venv/Scripts/activate -> git bash

deactivate

python app.py

python -m app.main      # CLI   --- REMOVIDO
python run_gui.py       # GUI   --- Iniciar programa


npm config set allow-scripts=opencode-ai --location=user

Reinstalar open code:
npm uninstall -g opencode-ai
npm cache clean --force
npm install -g opencode-ai
opencode --version

python app/services/revisao.py

dados = {
    **dados_transcricao,
    **dados_whisper
}