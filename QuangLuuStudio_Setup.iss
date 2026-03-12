; ============================================================
; Quang Lưu Studio - Inno Setup Installer Script
; ============================================================
; Build: Mở file này bằng Inno Setup Compiler → Compile (Ctrl+F9)
; Hoặc chạy: "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" QuangLuuStudio_Setup.iss
; ============================================================

#define MyAppName "Quang Luu Studio"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "Quang Luu"
#define MyAppExeName "QuangLuuStudio.exe"
#define MyAppURL "https://github.com/quang-luu-studio"

[Setup]
; Thông tin cơ bản
AppId={{B8F3E2A1-5D6C-4E7F-9A0B-1C2D3E4F5A6B}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}

; Thư mục cài đặt
DefaultDirName={autopf}\QuangLuuStudio
DefaultGroupName={#MyAppName}

; Output
OutputDir=installer_output
OutputBaseFilename=Setup_QuangLuuStudio_v{#MyAppVersion}_trial

; Icon
SetupIconFile=app_icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}

; Nén
Compression=lzma2
SolidCompression=yes

; Giao diện
WizardStyle=modern
DisableWelcomePage=no

; Yêu cầu quyền admin (vì cài vào Program Files)
PrivilegesRequired=admin

; Thông tin hiển thị
VersionInfoVersion={#MyAppVersion}
VersionInfoCompany={#MyAppPublisher}
VersionInfoProductName={#MyAppName}

; Cho phép người dùng chọn thư mục
DisableDirPage=no
DisableProgramGroupPage=yes

; Kiến trúc
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Tạo shortcut trên Desktop"; GroupDescription: "Shortcut:"
Name: "startmenuicon"; Description: "Tạo shortcut trong Start Menu"; GroupDescription: "Shortcut:"

[Files]
; File EXE chính (từ PyInstaller output)
Source: "dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion

; Icon
Source: "app_icon.ico"; DestDir: "{app}"; Flags: ignoreversion

; Script cài đặt loopMIDI + Surface
Source: "setup_all.bat"; DestDir: "{app}"; Flags: ignoreversion

; App config (không ghi đè nếu đã tồn tại — giữ cấu hình của user)
Source: "app_config.json"; DestDir: "{app}"; Flags: onlyifdoesntexist

; Studio One Surface files
Source: "studio_one\QuangLuuMIDI.surface.xml"; DestDir: "{app}\studio_one"; Flags: ignoreversion
Source: "studio_one\deviceinfo.xml"; DestDir: "{app}\studio_one"; Flags: ignoreversion

[Dirs]
; Tạo thư mục cho dữ liệu
Name: "{app}\temp_audio"; Permissions: users-full

[Icons]
; Shortcut trên Desktop
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\app_icon.ico"; Tasks: desktopicon
; Shortcut trong Start Menu
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\app_icon.ico"; Tasks: startmenuicon
; Shortcut gỡ cài đặt trong Start Menu
Name: "{autoprograms}\Gỡ cài đặt {#MyAppName}"; Filename: "{uninstallexe}"; Tasks: startmenuicon

[Run]
; Cài đặt loopMIDI + Surface sau khi cài đặt
Filename: "{app}\setup_all.bat"; Description: "Cài đặt loopMIDI và Surface cho Studio One"; Flags: nowait postinstall skipifsilent
; Chạy ứng dụng sau khi cài đặt (tùy chọn)
Filename: "{app}\{#MyAppExeName}"; Description: "Chạy {#MyAppName} ngay bây giờ"; Flags: nowait postinstall skipifsilent unchecked

[Code]
// Tạo các file JSON mặc định khi cài đặt lần đầu
procedure CurStepChanged(CurStep: TSetupStep);
var
  FilePath: String;
begin
  if CurStep = ssPostInstall then
  begin
    // Tạo activation.json mặc định (trống - chưa kích hoạt)
    FilePath := ExpandConstant('{app}\activation.json');
    if not FileExists(FilePath) then
      SaveStringToFile(FilePath, '{' + #13#10 + '    "activation_code": "",' + #13#10 + '    "activation_date": "",' + #13#10 + '    "activation_timestamp": 0' + #13#10 + '}', False);

    // Tạo settings.json mặc định (trống - chờ người dùng cấu hình)
    FilePath := ExpandConstant('{app}\settings.json');
    if not FileExists(FilePath) then
      SaveStringToFile(FilePath, '{' + #13#10 + '    "studio_one_path": "",' + #13#10 + '    "browser_path": "",' + #13#10 + '    "auto_launch_studio_one": false' + #13#10 + '}', False);

    // Tạo saved_songs.json mặc định (danh sách trống)
    FilePath := ExpandConstant('{app}\saved_songs.json');
    if not FileExists(FilePath) then
      SaveStringToFile(FilePath, '[]', False);

    // Tạo tone_cache.json mặc định (trống)
    FilePath := ExpandConstant('{app}\tone_cache.json');
    if not FileExists(FilePath) then
      SaveStringToFile(FilePath, '{}', False);

    // Tạo manual_timelines.json mặc định (trống)
    FilePath := ExpandConstant('{app}\manual_timelines.json');
    if not FileExists(FilePath) then
      SaveStringToFile(FilePath, '{}', False);
  end;
end;

[UninstallDelete]
; Xóa các file dữ liệu khi gỡ cài đặt
Type: files; Name: "{app}\activation.json"
Type: files; Name: "{app}\settings.json"
Type: files; Name: "{app}\saved_songs.json"
Type: files; Name: "{app}\tone_cache.json"
Type: files; Name: "{app}\manual_timelines.json"
Type: files; Name: "{app}\app_config.json"
Type: dirifempty; Name: "{app}\temp_audio"
Type: dirifempty; Name: "{app}"
