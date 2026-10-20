; =====================================================================
; Script Inno Setup para o SONAX Gratuito
; =====================================================================
#define MyAppName "SONAX Gratuito"
#define MyAppVersion "1.2.0"
#define MyAppPublisher "Falavinha Next"
#define MyAppExeName "SONAX_gratuito.exe"

[Setup]
; AppId exclusivo para a versao gratuita (evita conflito com a versao padrao)
AppId={{E9DA6257-35F2-4E54-9CB8-C9C886D62000}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\SONAX_gratuito
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=dist
OutputBaseFilename=Instalador_SONAX_gratuito
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
; Copia os arquivos gerados pelo PyInstaller na pasta dist\SONAX_gratuito (exceto .env)
Source: "dist\SONAX_gratuito\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: ".env"
; Copia o .env somente se nao existir no destino para nao sobrescrever chaves existentes
Source: "dist\SONAX_gratuito\.env"; DestDir: "{app}"; Flags: onlyifdoesntexist skipifsourcedoesntexist

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent
