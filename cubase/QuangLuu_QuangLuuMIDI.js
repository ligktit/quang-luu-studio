// Quang Luu Studio - script MIDI Remote cho Cubase (ban THAM DO, giai doan 0).
//
// Vai tro: thay cho QuangLuuMIDI.surface.xml cua Studio One. Cubase 12+ (moi ban
// Elements/Artist/Pro) tu nap file nay khi thay du hai cong loopMIDI:
//     QuangLuuMIDI  -> app GUI vao   (Cubase: MIDI Input)
//     QLS_PhanHoi   -> Cubase TRA ve (Cubase: MIDI Output)
//
// Vi tri cai (chay ThamDoCubase.bat -CaiScript, hoac chep tay):
//   %USERPROFILE%\Documents\Steinberg\Cubase\MIDI Remote\Driver Scripts\Local\QuangLuu\QuangLuuMIDI\QuangLuu_QuangLuuMIDI.js
// Sua xong bam "Reload Scripts" trong MIDI Remote Manager, khong can mo lai Cubase.
// Log xem o: Lower Zone -> MIDI Remote -> Scripting Tools -> Script Console.
//
// Ban tham do nay do 5 dieu truoc khi viet adapter Cubase trong app:
//   1. Cubase co nhan cong va TRA LOI ping (CC 49) khong, tre bao lau.
//   2. mOnTitleChange cua kenh mixer co bao ten track luc bai nap xong khong
//      -> dung lam tin hieu "san sang" thay cho hen gio +3/10/25/50s.
//   3. Mute/fader gan theo CHI SO kenh (khong theo ten) co trung voi bai mau khong.
//   4. Plugin o insert slot cua kenh Mic co nhung tham so nao (tag + ten + gia tri)
//      -> can cho key_root (CC 33) / scale_type (CC 35).
//   5. Fader 0 dB cua Cubase ung voi gia tri MIDI nao (Studio One: 76).
//
// Engine JS cua Cubase la ES5: KHONG dung let/const/arrow/template string.

var midiremote_api = require('midiremote_api_v1')

// ---- Hang so khop voi app_config.json (midi_cc) ---------------------------
var CC = {
    tone_music: 10, tone_voice: 11,
    mix_music: 20, mix_mic: 21, mix_reverb: 22, mix_backing: 23,
    key_root: 33, scale_type: 35,
    tone_auto: 40, fix_meo: 45, mode_danca: 46, be: 47, tat_on: 48,
    ready_ping: 49,
    mute_music: 50, mute_mic: 51, mute_reverb: 52, mute_backing: 53
}
var MIDI_CHANNEL = 0           // app luon gui channel 0 (core/midi.py)
var SO_KENH_THEO_DOI = 8       // bao nhieu kenh mixer dau tien duoc theo doi ten/fader
// Thu tu kenh BAT BUOC trong ban mau .cpr (MIDI Remote gan theo chi so, khong theo ten):
var KENH = { nhac: 0, mic: 1, vang: 2, be: 3 }
// Phan hoi ve app:
//   CC 49          : echo ping (dung gia tri vua nhan)
//   CC 60 + i      : ten kenh i vua doi; gia tri = do dai ten (0 = kenh trong/khong co)
//   CC 20..23      : fader kenh thay doi (do fader law: keo fader ve 0 dB roi doc gia tri)
//   CC 50..53      : mute kenh thay doi
//   CC 70          : plugin o insert slot doi; gia tri = so tham so dem duoc (toi da 127)
var CC_TEN_KENH_GOC = 60
var CC_PLUGIN = 70

// ---- Driver + cong -----------------------------------------------------------
var deviceDriver = midiremote_api.makeDeviceDriver('QuangLuu', 'QuangLuuMIDI', 'Quang Luu Studio')
var midiInput  = deviceDriver.mPorts.makeMidiInput('QuangLuuMIDI')
var midiOutput = deviceDriver.mPorts.makeMidiOutput('QLS_PhanHoi')

deviceDriver.makeDetectionUnit().detectPortPair(midiInput, midiOutput)
    .expectInputNameEquals('QuangLuuMIDI')
    .expectOutputNameEquals('QLS_PhanHoi')

function guiCC(activeDevice, cc, value) {
    var v = Math.round(value)
    if (v < 0) v = 0
    if (v > 127) v = 127
    midiOutput.sendMidi(activeDevice, [0xB0 | MIDI_CHANNEL, cc & 0x7F, v])
}

function log(s) { console.log('[QLS] ' + s) }

// Gui mot chuoi ASCII ve app bang SysEx: F0 7D 'Q' 'L' <loai> <byte...> F7 (moi byte < 0x80).
// Dung de doc danh sach tham so plugin ma khong can mo Script Console.
function guiSysEx(activeDevice, loai, text) {
    var bytes = [0xF0, 0x7D, 0x51, 0x4C, loai & 0x7F]
    for (var i = 0; i < text.length && i < 200; i++) {
        var c = text.charCodeAt(i)
        bytes.push(c < 0x80 ? c : 0x3F)
    }
    bytes.push(0xF7)
    midiOutput.sendMidi(activeDevice, bytes)
}

var surface = deviceDriver.mSurface
var page = deviceDriver.mMapping.makePage('QuangLuu')
var currentMapping = null

// Tao mot knob nhan CC. Moi callback cua host chi chay khi co surface element
// dang bind, nen ke ca thu chi can "nghe" cung phai co knob (de nho, ngoai tam nhin).
var _x = 0
function knobCC(cc) {
    var k = surface.makeKnob(_x, 0, 1, 1)
    _x += 1
    k.mSurfaceValue.mMidiBinding.setInputPort(midiInput).bindToControlChange(MIDI_CHANNEL, cc)
    return k
}
function buttonCC(cc) {
    var b = surface.makeButton(_x, 2, 1, 1)
    _x += 1
    b.mSurfaceValue.mMidiBinding.setInputPort(midiInput).bindToControlChange(MIDI_CHANNEL, cc)
    return b
}

// ---- 1. Ping / echo ------------------------------------------------------------
var knobPing = knobCC(CC.ready_ping)
knobPing.mSurfaceValue.mOnProcessValueChange = function (activeDevice, value, diff) {
    var v = Math.round(value * 127)
    guiCC(activeDevice, CC.ready_ping, v)
    log('ping ' + v + ' -> echo')
}

// ---- 2+3+5. Kenh mixer theo chi so: ten, fader, mute ----------------------------
var bankZone = page.mHostAccess.mMixConsole.makeMixerBankZone('QuangLuuKenh')
    .excludeInputChannels()
    .excludeOutputChannels()
    .setFollowVisibility(false)

var faderCCTheoKenh = {}
faderCCTheoKenh[KENH.nhac] = CC.mix_music
faderCCTheoKenh[KENH.mic] = CC.mix_mic
faderCCTheoKenh[KENH.vang] = CC.mix_reverb
faderCCTheoKenh[KENH.be] = CC.mix_backing
var muteCCTheoKenh = {}
muteCCTheoKenh[KENH.nhac] = CC.mute_music
muteCCTheoKenh[KENH.mic] = CC.mute_mic
muteCCTheoKenh[KENH.vang] = CC.mute_reverb
muteCCTheoKenh[KENH.be] = CC.mute_backing

var kenh = []
for (var i = 0; i < SO_KENH_THEO_DOI; i++) {
    (function (idx) {
        var ch = bankZone.makeMixerBankChannel()
        kenh.push(ch)

        // Fader: kenh 0..3 nhan CC that cua app, kenh con lai dung CC gia (100+idx) chi de co binding.
        var fcc = faderCCTheoKenh.hasOwnProperty(idx) ? faderCCTheoKenh[idx] : 116 + idx
        var kFader = knobCC(fcc)
        page.makeValueBinding(kFader.mSurfaceValue, ch.mValue.mVolume)

        var mcc = muteCCTheoKenh.hasOwnProperty(idx) ? muteCCTheoKenh[idx] : 120 + idx
        var bMute = buttonCC(mcc)
        page.makeValueBinding(bMute.mSurfaceValue, ch.mValue.mMute)

        // Ten kenh doi = bai da nap toi muc mixer co track. Day la tin hieu "san sang".
        ch.mValue.mVolume.mOnTitleChange = function (activeDevice, activeMapping, objectTitle, valueTitle) {
            var len = objectTitle ? objectTitle.length : 0
            if (len > 0) log('kenh[' + idx + '] ten="' + objectTitle + '"')
            guiCC(activeDevice, CC_TEN_KENH_GOC + idx, len)
        }
        // Fader: in ca gia tri 0..1 lan chu hien thi (dB) de doc duoc "0 dB = ?".
        ch.mValue.mVolume.mOnProcessValueChange = function (activeDevice, activeMapping, value) {
            if (faderCCTheoKenh.hasOwnProperty(idx)) guiCC(activeDevice, faderCCTheoKenh[idx], value * 127)
        }
        ch.mValue.mVolume.mOnDisplayValueChange = function (activeDevice, activeMapping, value, units) {
            if (idx === KENH.mic) log('fader Mic hien thi "' + value + ' ' + units + '"')
        }
        ch.mValue.mMute.mOnProcessValueChange = function (activeDevice, activeMapping, value) {
            if (muteCCTheoKenh.hasOwnProperty(idx)) guiCC(activeDevice, muteCCTheoKenh[idx], value > 0.5 ? 127 : 0)
        }
    })(i)
}

// ---- 4. Plugin o insert slot kenh Mic: tham so theo CHI SO (API Cubase 13.0) ----------------
// Cubase 13.0.10 KHONG co DirectAccess/accessSlotAtIndex (xem .api/v1/midiremote_api_v1.d.ts).
// Chi co: makeInsertEffectViewer().excludeEmptySlots() -> viewer tro vao slot co plugin dau tien,
// va mParameterBankZone.makeParameterValue() lay tham so theo thu tu cua plugin (Remote Control Editor).
// Cach lam: tao SO_THAM_SO gia tri, bind moi gia tri vao mot knob CC (CC_THAM_SO_GOC + i).
//   -> app gui CC 80+i de dat tham so i (0..127 ~ 0..1). Ten/gia tri hien thi gui ve bang SysEx
//      (loai 1: param|i|ten, loai 4: disp|i|gia_tri|don_vi), app tu tim chi so cua "Key"/"Scale".
var SO_THAM_SO = 32
var CC_THAM_SO_GOC = 80          // CC 80..111
var insertViewer = kenh[KENH.mic].mInsertAndStripEffects.makeInsertEffectViewer('QuangLuuInsertMic').excludeEmptySlots()
var thamSo = []
for (var pi = 0; pi < SO_THAM_SO; pi++) {
    (function (i) {
        var pv = insertViewer.mParameterBankZone.makeParameterValue()
        var k = knobCC(CC_THAM_SO_GOC + i)
        page.makeValueBinding(k.mSurfaceValue, pv)
        pv.mOnTitleChange = function (activeDevice, activeMapping, objectTitle, valueTitle) {
            if (objectTitle && objectTitle.length) {
                log('param[' + i + '] "' + objectTitle + '" / "' + valueTitle + '"')
                guiSysEx(activeDevice, 0x01, 'param|' + i + '|' + objectTitle + '|' + valueTitle)
            }
        }
        pv.mOnDisplayValueChange = function (activeDevice, activeMapping, value, units) {
            guiSysEx(activeDevice, 0x04, 'disp|' + i + '|' + value + '|' + units)
        }
        thamSo.push(pv)
    })(pi)
}
// App gui key_root (CC 33), scale_type (CC 35), tone_auto (CC 40) nhu voi Studio One.
// Chi so tham so cua Steinberg Pitch Correct (do 2026-10-04): 6 Key, 7 Scale, 3 PitchCorrect.
// Dung plugin khac thi doi 3 so nay (xem bang param|i|ten qua SysEx).
var THAM_SO_PLUGIN = { key_root: 6, scale_type: 7, tone_auto: 3 }
var ccTheoKhoa = { key_root: CC.key_root, scale_type: CC.scale_type, tone_auto: CC.tone_auto }
for (var khoa in THAM_SO_PLUGIN) {
    if (!THAM_SO_PLUGIN.hasOwnProperty(khoa)) continue
    var kApp = knobCC(ccTheoKhoa[khoa])
    page.makeValueBinding(kApp.mSurfaceValue, thamSo[THAM_SO_PLUGIN[khoa]])
}
insertViewer.mOnChangePluginIdentity = function (activeDevice, activeMapping, pluginName, pluginVendor, pluginVersion, formatVersion) {
    log('plugin "' + pluginName + '" (' + pluginVendor + ' ' + pluginVersion + '/' + formatVersion + ')')
    guiSysEx(activeDevice, 0x02, 'plugin|' + pluginName + '|' + pluginVendor + '|' + pluginVersion)
    guiCC(activeDevice, CC_PLUGIN, 1)
}
insertViewer.mOnTitleChange = function (activeDevice, activeMapping, title) {
    log('insert viewer title "' + title + '"')
    guiSysEx(activeDevice, 0x05, 'viewer|' + title)
}

// Cac CC con lai cua app: chi ghi log de biet Cubase CO nhan duoc (gan vao dau la viec cua giai doan 2).
var ccChiLog = [CC.tone_music, CC.tone_voice, CC.fix_meo, CC.mode_danca, CC.be, CC.tat_on, 30, 31, 32, 34, 36, 37, 38, 39, 41, 42, 43, 44, 54]
for (var c = 0; c < ccChiLog.length; c++) {
    (function (cc) {
        var k = knobCC(cc)
        k.mSurfaceValue.mOnProcessValueChange = function (activeDevice, value, diff) {
            log('nhan CC ' + cc + ' = ' + Math.round(value * 127) + ' (chua gan)')
        }
    })(ccChiLog[c])
}

// ---- Vong doi ----------------------------------------------------------------
page.mOnActivate = function (activeDevice, activeMapping) {
    currentMapping = activeMapping
    log('page active - script da nap, dang cho ping')
    guiCC(activeDevice, 71, 1)
    guiSysEx(activeDevice, 0x03, 'page_active')
}
page.mOnDeactivate = function (activeDevice, activeMapping) {
    currentMapping = null
}
deviceDriver.mOnActivate = function (activeDevice) {
    log('driver active: Cubase da thay QuangLuuMIDI + QLS_PhanHoi')
    guiCC(activeDevice, 72, 1)
}
deviceDriver.mOnDeactivate = function (activeDevice) {
    log('driver inactive')
}
