; Instalador Windows do Baixador (Inno Setup 6).
;
; Buildar:
;   1) server/.venv/Scripts/python.exe -m PyInstaller Baixador.spec --noconfirm
;   2) "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" Baixador.iss
;
; Saida: Baixador-Setup-v<versao>.exe na raiz do projeto.
;
; A v1.0.0 foi empacotada a mao, sem script no repo. Este arquivo existe pra que
; o instalador volte a ser reproduzivel a partir do fonte.

#define AppName "Baixador"
#define AppVersion "1.1.1"
#define AppExe "Baixador.exe"

[Setup]
; NAO MUDE O AppId. Ele foi recuperado do registro da v1.0.0 (chave
; HKCU\...\Uninstall\{4F3A2F1C-6E2B-4F8E-B5E3-BAIXADOR000001}}_is1) e e o que faz
; esta versao ATUALIZAR a instalacao existente em vez de instalar do lado.
; Nao e um GUID valido (BAIXADOR000001 nao e hexadecimal) e tem uma chave extra no
; fim -- foi escrito a mao na v1.0.0. Esta reproduzido aqui exatamente como esta
; no registro; "consertar" pra um GUID de verdade quebraria o update de quem ja tem
; a v1.0.0 instalada.
AppId={{4F3A2F1C-6E2B-4F8E-B5E3-BAIXADOR000001}}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
; Mesmo destino da v1.0.0. Quando o AppId bate, o Inno reusa o diretorio da
; instalacao anterior de qualquer forma; isto aqui e pra instalacao nova ficar igual.
DefaultDirName={localappdata}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
; Instalacao por usuario: o app so escreve em HKCU (autostart) e LOCALAPPDATA (log),
; entao nao ha motivo pra pedir admin.
PrivilegesRequired=lowest
OutputDir=.
OutputBaseFilename=Baixador-Setup-v{#AppVersion}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
; O Baixador fica na bandeja; sem isso o update falha com arquivo em uso.
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "Criar atalho na area de trabalho"; GroupDescription: "Atalhos:"
Name: "autostart"; Description: "Iniciar o Baixador junto com o Windows"; GroupDescription: "Inicializacao:"; Flags: unchecked

[Files]
Source: "dist\Baixador\{#AppExe}"; DestDir: "{app}"; Flags: ignoreversion
Source: "dist\Baixador\_internal\*"; DestDir: "{app}\_internal"; Flags: ignoreversion recursesubdirs createallsubdirs
; A extensao do Chrome vai junto: e nela que ficam os controles (formato, qualidade).
; Carregue em chrome://extensions > Modo do desenvolvedor > Carregar sem compactacao,
; apontando pra {app}\extension.
Source: "extension\*"; DestDir: "{app}\extension"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{group}\Pasta da extensao do Chrome"; Filename: "{app}\extension"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "Baixador"; ValueData: """{app}\{#AppExe}"""; Flags: uninsdeletevalue; Tasks: autostart

[Run]
Filename: "{app}\{#AppExe}"; Description: "Iniciar o Baixador agora"; Flags: nowait postinstall skipifsilent
Filename: "{app}\extension"; Description: "Abrir a pasta da extensao (pra carregar no Chrome)"; Flags: shellexec nowait postinstall skipifsilent unchecked

[UninstallDelete]
Type: filesandordirs; Name: "{app}\_internal"
Type: filesandordirs; Name: "{app}\extension"
