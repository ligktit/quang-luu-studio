; ============================================================
; Quang Lưu Studio - Inno Setup Installer Script
; ============================================================
; Build: Mở file này bằng Inno Setup Compiler → Compile (Ctrl+F9)
; Hoặc chạy: "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" QuangLuuStudio_Setup.iss
; ============================================================
;
; File Layout:
;   {app}\               → Program files (read-only)
;   {userappdata}\QuangLuuStudio\ → User data (writable)
;   {userdocs}\QuangLuuStudio\    → Recordings (writable)
; ============================================================

#define MyAppName "Quang Luu Studio"
#define MyAppVersion "1.5.1"
#define MyAppPublisher "Quang Luu"
#define MyAppExeName "QuangLuuStudio.exe"
#define MyAppURL "https://github.com/ligktit/quang-luu-studio"
#define MyAppDataFolder "QuangLuuStudio"

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
OutputBaseFilename=Setup_QuangLuuStudio_v{#MyAppVersion}

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
; === PROGRAM FILES (read-only, {app}) ===

; File EXE chính (từ PyInstaller output)
Source: "dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion

; Icon
Source: "app_icon.ico"; DestDir: "{app}"; Flags: ignoreversion

; Script cài đặt loopMIDI + Surface
Source: "setup_all.bat"; DestDir: "{app}"; Flags: ignoreversion
; Script cấu hình YouTube cookies
Source: "configure_youtube_cookies.bat"; DestDir: "{app}"; Flags: ignoreversion

; App config — MIDI mapping (admin editable, không ghi đè nếu đã tồn tại)
Source: "app_config.json"; DestDir: "{app}"; Flags: onlyifdoesntexist

; Studio One Surface files
Source: "studio_one\QuangLuuMIDI.surface.xml"; DestDir: "{app}\studio_one"; Flags: ignoreversion
Source: "studio_one\deviceinfo.xml"; DestDir: "{app}\studio_one"; Flags: ignoreversion

; SFX (sound effects)
Source: "sfx\*"; DestDir: "{app}\sfx"; Flags: ignoreversion recursesubdirs

; Model giọng nói tiếng Việt (offline) — đặt CẠNH exe, không nhúng vào exe để
; tránh phình + giải nén lại mỗi lần chạy. Tải trước bằng tools/download_voice_models.py.
; skipifsourcedoesntexist: build không có model vẫn chạy được (tính năng fail-soft).
Source: "models\*"; DestDir: "{app}\models"; Flags: ignoreversion recursesubdirs skipifsourcedoesntexist
; Piper TTS binary (Windows)
Source: "tools\piper\*"; DestDir: "{app}\tools\piper"; Flags: ignoreversion recursesubdirs skipifsourcedoesntexist

[Dirs]
; Tạo thư mục cho dữ liệu user (writable)
Name: "{userappdata}\{#MyAppDataFolder}"; Permissions: users-full
; Tạo thư mục cho recordings
Name: "{userdocs}\{#MyAppDataFolder}"; Permissions: users-full

[Icons]
; Shortcut trên Desktop
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\app_icon.ico"; Tasks: desktopicon
; Shortcut trong Start Menu
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\app_icon.ico"; Tasks: startmenuicon
; Shortcut gỡ cài đặt trong Start Menu
Name: "{autoprograms}\Gỡ cài đặt {#MyAppName}"; Filename: "{uninstallexe}"; Tasks: startmenuicon
; Shortcut cấu hình YouTube Cookies
Name: "{autoprograms}\{#MyAppName} - Cấu hình YouTube Cookies"; Filename: "{app}\configure_youtube_cookies.bat"; Tasks: startmenuicon
; Shortcut mở thư mục Recordings
Name: "{autoprograms}\{#MyAppName} Recordings"; Filename: "{userdocs}\{#MyAppDataFolder}"; Tasks: startmenuicon

[Run]
; Cài đặt loopMIDI + Surface sau khi cài đặt
Filename: "{app}\setup_all.bat"; Description: "Cài đặt loopMIDI và Surface cho Studio One"; Flags: nowait postinstall skipifsilent
; Chạy ứng dụng sau khi cài đặt (tùy chọn)
Filename: "{app}\{#MyAppExeName}"; Description: "Chạy {#MyAppName} ngay bây giờ"; Flags: nowait postinstall skipifsilent unchecked

[Code]
// ── Tạo các file JSON mặc định khi cài đặt lần đầu ──
// File được tạo trong %APPDATA%\QuangLuuStudio\ (user-writable)
procedure CreateDefaultDataFiles();
var
  DataDir, FilePath: String;
begin
  DataDir := ExpandConstant('{userappdata}\{#MyAppDataFolder}');
  ForceDirectories(DataDir);

  // activation.json
  FilePath := DataDir + '\activation.json';
  if not FileExists(FilePath) then
    SaveStringToFile(FilePath,
      '{' + #13#10 +
      '    "activation_code": "",' + #13#10 +
      '    "activation_date": "",' + #13#10 +
      '    "activation_timestamp": 0' + #13#10 +
      '}', False);

  // settings.json
  FilePath := DataDir + '\settings.json';
  if not FileExists(FilePath) then
    SaveStringToFile(FilePath,
      '{' + #13#10 +
      '    "studio_one_path": "",' + #13#10 +
      '    "browser_path": "",' + #13#10 +
      '    "auto_launch_studio_one": false' + #13#10 +
      '}', False);

  // saved_songs.json
  FilePath := DataDir + '\saved_songs.json';
  if not FileExists(FilePath) then
    SaveStringToFile(FilePath, '[]', False);

  // tone_cache.json
  FilePath := DataDir + '\tone_cache.json';
  if not FileExists(FilePath) then
    SaveStringToFile(FilePath, '{}', False);

  // manual_timelines.json
  FilePath := DataDir + '\manual_timelines.json';
  if not FileExists(FilePath) then
    SaveStringToFile(FilePath, '{}', False);
end;

// ── Migration: di chuyển file JSON cũ từ {app} sang {userappdata} ──
// Chạy khi upgrade từ v1.0 (file nằm cạnh exe) sang v1.1+ (%APPDATA%)
procedure MigrateOldDataFiles();
var
  AppDir, DataDir, OldPath, NewPath: String;
  Files: array of String;
  I: Integer;
begin
  AppDir := ExpandConstant('{app}');
  DataDir := ExpandConstant('{userappdata}\{#MyAppDataFolder}');

  SetArrayLength(Files, 5);
  Files[0] := 'settings.json';
  Files[1] := 'saved_songs.json';
  Files[2] := 'activation.json';
  Files[3] := 'tone_cache.json';
  Files[4] := 'manual_timelines.json';

  for I := 0 to GetArrayLength(Files) - 1 do
  begin
    OldPath := AppDir + '\' + Files[I];
    NewPath := DataDir + '\' + Files[I];
    // Chỉ migrate nếu file cũ tồn tại VÀ file mới chưa có
    if FileExists(OldPath) and (not FileExists(NewPath)) then
    begin
      FileCopy(OldPath, NewPath, False);
      Log('Migrated: ' + OldPath + ' -> ' + NewPath);
      // Xóa file cũ sau khi copy thành công
      DeleteFile(OldPath);
    end;
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    // 1. Migrate file cũ (nếu upgrade từ v1.0)
    MigrateOldDataFiles();
    // 2. Tạo file mặc định (nếu chưa có)
    CreateDefaultDataFiles();
  end;
end;

// ── Uninstall: hỏi người dùng có muốn xóa dữ liệu không ──
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataDir, DocsDir: String;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    DataDir := ExpandConstant('{userappdata}\{#MyAppDataFolder}');
    DocsDir := ExpandConstant('{userdocs}\{#MyAppDataFolder}');

    if DirExists(DataDir) then
    begin
      if MsgBox(
        'Bạn có muốn xóa dữ liệu cá nhân (settings, danh sách bài hát, cache)?' + #13#10 + #13#10 +
        'Thư mục: ' + DataDir + #13#10 + #13#10 +
        'Nhấn "Có" để xóa hoàn toàn.' + #13#10 +
        'Nhấn "Không" để giữ lại (có thể dùng lại khi cài lại).',
        mbConfirmation, MB_YESNO) = IDYES then
      begin
        DelTree(DataDir, True, True, True);
      end;
    end;

    if DirExists(DocsDir) then
    begin
      if MsgBox(
        'Bạn có muốn xóa thư mục Recordings?' + #13#10 + #13#10 +
        'Thư mục: ' + DocsDir + #13#10 + #13#10 +
        'Nhấn "Có" để xóa tất cả file ghi âm.' + #13#10 +
        'Nhấn "Không" để giữ lại.',
        mbConfirmation, MB_YESNO) = IDYES then
      begin
        DelTree(DocsDir, True, True, True);
      end;
    end;
  end;
end;

[UninstallDelete]
; Xóa file program-level (luôn xóa khi gỡ)
Type: files; Name: "{app}\app_config.json"
Type: filesandordirs; Name: "{app}\sfx"
Type: filesandordirs; Name: "{app}\studio_one"
; Xóa file cũ nếu còn sót từ v1.0 (migration đã chạy nhưng có thể bị bỏ qua)
Type: files; Name: "{app}\activation.json"
Type: files; Name: "{app}\settings.json"
Type: files; Name: "{app}\saved_songs.json"
Type: files; Name: "{app}\tone_cache.json"
Type: files; Name: "{app}\manual_timelines.json"
Type: filesandordirs; Name: "{app}\temp_audio"
Type: dirifempty; Name: "{app}"
; Dữ liệu user trong %APPDATA% và Documents được xử lý bởi [Code] ở trên
; (hỏi người dùng có muốn xóa không)
