; ============================================================
; Quang Lưu Studio — BỘ CÀI CẦU NỐI (máy ≤ 1.8.x cài bằng Inno → bản Velopack)
; ============================================================
; Máy cũ nhận file này qua bộ cập nhật cũ (server /api/v1/updates/check → /download,
; theo rollout_percent). Toàn bộ việc nằm trong PrepareToInstall:
;   1. dừng app cũ đang chạy trong {app} (bộ cập nhật cũ không tự thoát được);
;   2. cài Velopack (QuangLuuStudio-CaiDat.exe --silent) dưới quyền NGƯỜI DÙNG GỐC
;      → vào %LocalAppData% của người hát, không phải của tài khoản admin;
;      hỏng → dừng hẳn, bản cũ còn nguyên;
;   3. dừng app mới nếu Setup Velopack đã tự mở nó;
;   4. chuyển app_config.json cũ sang lớp người dùng (exe mới --chuyen-cau-hinh-cu);
;   5. CHỈ KHI bước 4 xong: dọn bản cũ bằng tools\don_ban_cu.ps1 (KHÔNG gọi
;      unins000.exe — nó hỏi "Xoá dữ liệu?" mà /SUPPRESSMSGBOXES không chặn);
;      bước 4 hỏng → giữ bản cũ, app mới tự chuyển + hỏi dọn ở lần chạy đầu;
;   6. mở app mới dưới quyền người dùng gốc.
; Build: ISCC.exe /DVelopackDir=releases QuangLuuStudio_Bridge.iss
; Log: %TEMP%\Setup Log *.txt (SetupLogging).
; ============================================================

#define MyAppName "Quang Luu Studio"
#define MyAppVersion "1.9.0"
#define MyAppPublisher "Quang Luu"
#ifndef VelopackDir
  #define VelopackDir "releases"
#endif

[Setup]
AppId={{B8F3E2A1-5D6C-4E7F-9A0B-1C2D3E4F5A6B}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\QuangLuuStudio
UsePreviousAppDir=yes
DisableDirPage=yes
DisableProgramGroupPage=yes
DisableReadyPage=yes
DisableFinishedPage=yes
PrivilegesRequired=admin
; Không tạo/sửa mục gỡ cài đặt: bản Velopack có mục gỡ riêng (HKCU).
Uninstallable=no
CloseApplications=no
RestartApplications=no
SetupLogging=yes
OutputDir=installer_output
OutputBaseFilename=Setup_QuangLuuStudio_v{#MyAppVersion}
SetupIconFile=app_icon.ico
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
Source: "{#VelopackDir}\QuangLuuStudio-CaiDat.exe"; Flags: dontcopy
Source: "tools\don_ban_cu.ps1"; Flags: dontcopy

[Code]
const
  NewExeRel = 'QuangLuuStudio\current\QuangLuuStudio.exe';

var
  { Mã thoát của script dọn bản cũ; -1 = chưa chạy. }
  CleanupCode: Integer;

{ Chuỗi PowerShell trong nháy đơn: ' → '' }
function PsLit(S: String): String;
begin
  StringChangeEx(S, '''', '''''', True);
  Result := '''' + S + '''';
end;

{ Chạy một lệnh PowerShell (chỉ dùng nháy đơn bên trong). try/catch để lỗi ra mã 1 —
  không thì $null/ngoại lệ vẫn thoát 0. }
function RunPs(Cmd: String; AsOriginalUser: Boolean; var Code: Integer): Boolean;
var
  Params: String;
begin
  Params := '-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -Command "$ErrorActionPreference=''Stop''; try { ' + Cmd + ' } catch { exit 1 }"';
  if AsOriginalUser then
    Result := ExecAsOriginalUser('powershell.exe', Params, '', SW_HIDE, ewWaitUntilTerminated, Code)
  else
    Result := Exec('powershell.exe', Params, '', SW_HIDE, ewWaitUntilTerminated, Code);
  Log('PS rc=' + IntToStr(Code) + ': ' + Cmd);
end;

{ Bước 1 đã dừng app cũ; nếu cài bản mới hỏng thì mở lại bản cũ cho người hát. }
procedure RelaunchOldApp(AppDir: String);
var
  Rc: Integer;
  OldExe: String;
begin
  OldExe := AddBackslash(AppDir) + 'QuangLuuStudio.exe';
  if FileExists(OldExe) then
    ExecAsOriginalUser(OldExe, '', AppDir, SW_SHOWNORMAL, ewNoWait, Rc);
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  AppDir, CaiDat, Script: String;
  Code: Integer;
begin
  Result := '';
  CleanupCode := -1;
  AppDir := ExpandConstant('{app}');

  { 1. App cũ nằm trong thư mục cài cũ (AppDir) }
  RunPs('Get-Process QuangLuuStudio -ErrorAction SilentlyContinue | Where-Object { $_.Path -and $_.Path.StartsWith(' +
        PsLit(AddBackslash(AppDir)) + ', [StringComparison]::OrdinalIgnoreCase) } | Stop-Process -Force -ErrorAction SilentlyContinue; Start-Sleep -Seconds 1; exit 0',
        False, Code);

  { 2. Cài Velopack dưới quyền người dùng gốc }
  ExtractTemporaryFile('QuangLuuStudio-CaiDat.exe');
  CaiDat := ExpandConstant('{tmp}\QuangLuuStudio-CaiDat.exe');
  if (not ExecAsOriginalUser(CaiDat, '--silent', '', SW_HIDE, ewWaitUntilTerminated, Code)) or (Code <> 0) then
  begin
    Result := 'Chưa cài được bản mới (mã ' + IntToStr(Code) + '). Bản cũ vẫn dùng bình thường. ' +
              'Tải bộ cài tại https://qlstudio.duckdns.org/tai-ve hoặc liên hệ kỹ thuật viên.';
    RelaunchOldApp(AppDir);
    exit;
  end;
  if (not RunPs('if (Test-Path -LiteralPath (Join-Path $env:LOCALAPPDATA ' + PsLit(NewExeRel) + ')) { exit 0 } else { exit 2 }', True, Code)) or (Code <> 0) then
  begin
    Result := 'Đã chạy bộ cài mới nhưng không thấy app trong %LocalAppData%\QuangLuuStudio. ' +
              'Bản cũ vẫn dùng bình thường — liên hệ kỹ thuật viên.';
    RelaunchOldApp(AppDir);
    exit;
  end;

  { 3. Setup Velopack có thể đã tự mở app mới — đóng lại trước khi chuyển cấu hình/dọn }
  RunPs('Get-Process QuangLuuStudio -ErrorAction SilentlyContinue | Where-Object { $_.Path -like ''*\QuangLuuStudio\current\QuangLuuStudio.exe'' } | Stop-Process -Force -ErrorAction SilentlyContinue; exit 0',
        False, Code);

  { 4. Chuyển cấu hình (exe GUI → Start-Process -Wait để lấy mã thoát). \" là nháy kép
    thật sau khi Windows tách tham số: đường dẫn có dấu cách đi nguyên một đối số. }
  if RunPs('$p = Start-Process -FilePath (Join-Path $env:LOCALAPPDATA ' + PsLit(NewExeRel) +
           ') -ArgumentList @(''--chuyen-cau-hinh-cu'', ' + PsLit('\"' + AppDir + '\"') +
           ') -Wait -PassThru; if ($null -eq $p) { exit 1 }; if ($null -eq $p.ExitCode) { exit 1 }; exit $p.ExitCode', True, Code) and (Code = 0) then
  begin
    { 5. Dọn bản cũ (đang chạy quyền admin). Không xoá được hết → mã 2/3, app mới hỏi lại. }
    ExtractTemporaryFile('don_ban_cu.ps1');
    Script := ExpandConstant('{tmp}\don_ban_cu.ps1');
    if Exec('powershell.exe', '-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "' + Script +
         '" -LegacyDir "' + AppDir + '" -ProtectedDirs "' + ExpandConstant('{localappdata}') + '\QuangLuuStudio"',
         '', SW_HIDE, ewWaitUntilTerminated, Code) then
      CleanupCode := Code;
    Log('don_ban_cu.ps1 rc=' + IntToStr(CleanupCode));
  end
  else
    Log('Chuyển cấu hình cũ lỗi (rc=' + IntToStr(Code) + ') — giữ bản cũ, app mới tự xử lý ở lần chạy đầu');

  { 6. Mở app mới }
  RunPs('Start-Process -FilePath (Join-Path $env:LOCALAPPDATA ' + PsLit(NewExeRel) + '); exit 0', True, Code);
end;

{ Inno tạo lại thư mục cài rỗng ở ssInstall (CreateAppDir=yes) sau khi don_ban_cu.ps1 đã xoá nó.
  Chỉ khi dọn xong hoàn toàn (mã 0) mới bỏ thư mục rỗng này; RemoveDir không xoá thư mục có file. }
procedure CurStepChanged(CurStep: TSetupStep);
begin
  if (CurStep = ssPostInstall) and (CleanupCode = 0) then
  begin
    if RemoveDir(ExpandConstant('{app}')) then
      Log('Đã bỏ thư mục cài rỗng do Inno tạo lại')
    else
      Log('Không bỏ được thư mục cài (còn file hoặc đang bị giữ)');
  end;
end;
