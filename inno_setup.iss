; =====================================================================
; Script Inno Setup para o SONAX
; =====================================================================
#define MyAppName "SONAX"
#define MyAppVersion "1.2.0"
#define MyAppPublisher "Falavinha Next"
#define MyAppExeName "SONAX.exe"

[Setup]
AppId={{D8C95146-24E1-4F43-855A-B8B775C51999}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=dist
OutputBaseFilename=Instalador_SONAX
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
; Nao exige privilegio de administrador (instala no diretorio do usuario)
PrivilegesRequired=lowest
CloseApplications=yes

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
; Copia os arquivos gerados pelo PyInstaller na pasta dist\SONAX (exceto .env)
Source: "dist\SONAX\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: ".env"
; Copia o .env somente se nao existir no destino para nao sobrescrever chaves existentes
Source: "dist\SONAX\.env"; DestDir: "{app}"; Flags: onlyifdoesntexist skipifsourcedoesntexist

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent
