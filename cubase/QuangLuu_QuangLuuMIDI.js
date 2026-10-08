// Quang Luu Studio - script MIDI Remote cho Cubase.
//
// Vai tro: thay cho QuangLuuMIDI.surface.xml cua Studio One. Cubase 12+ (moi ban
// Elements/Artist/Pro) tu nap file nay khi thay du hai cong loopMIDI:
//     QuangLuuMIDI  -> app GUI vao   (Cubase: MIDI Input)
//     QLS_PhanHoi   -> Cubase TRA ve (Cubase: MIDI Output)
//
// Vi tri cai (setup_all.bat trong thu muc cai app chep vao; huong dan: cubase\HUONG_DAN_CAI_DAT_CUBASE.md):
//   <Documents>\Steinberg\Cubase\MIDI Remote\Driver Scripts\Local\QuangLuu\QuangLuuMIDI\QuangLuu_QuangLuuMIDI.js
// Sua xong bam "Reload Scripts" trong MIDI Remote Manager (hoac mo lai Cubase).
// Log xem o: Lower Zone -> MIDI Remote -> Scripting Tools -> Script Console.
//
// QLS_SCRIPT_VERSION: setup_all.bat va QLS_ChanDoan doc dong nay (va log 'driver active') de biet may khach chay ban nao.
var QLS_SCRIPT_VERSION = '2026-10-08'
//
// Ban dau day la ban tham do, do 5 dieu truoc khi viet adapter Cubase trong app:
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

// ---- 2+3+5. Kenh mixer: gom NHOM theo ten kenh, fader/mute cua app dieu khien ca nhom --------
// App chi co 4 fader/mute (nhac, mic, vang, be) nhung bai cua khach co nhieu kenh hon (vi du 3 FX:
// "Vang dai", "Delay", "Vang ngan"). Moi kenh duoc xep vao mot nhom theo TEN (mOnTitleChange);
// khong doan duoc ten thi dung chi so du phong 0 nhac / 1 mic / 2 vang / 3 be (ban mau may dev).
//   - Nhom 1 kenh: fader app = fader kenh (tuyet doi, nhu truoc: Mic 0 dB = CC 100).
//   - Nhom nhieu kenh: fader app = fader KENH DAU nhom (tuyet doi), cac kenh sau giu nguyen chenh lech
//     so voi kenh dau nhu dang co trong Cubase (do lai moi khi keo tay mot kenh trong nhom).
//   - Mute app = mute moi kenh trong nhom.
var bankZone = page.mHostAccess.mMixConsole.makeMixerBankZone('QuangLuuKenh')
    .excludeInputChannels()
    .excludeOutputChannels()
    .setFollowVisibility(false)

var NHOM = ['nhac', 'mic', 'vang', 'be']
var faderCCTheoNhom = { nhac: CC.mix_music, mic: CC.mix_mic, vang: CC.mix_reverb, be: CC.mix_backing }
var muteCCTheoNhom = { nhac: CC.mute_music, mic: CC.mute_mic, vang: CC.mute_reverb, be: CC.mute_backing }
var nhomTheoChiSo = {}
nhomTheoChiSo[KENH.nhac] = 'nhac'
nhomTheoChiSo[KENH.mic] = 'mic'
nhomTheoChiSo[KENH.vang] = 'vang'
nhomTheoChiSo[KENH.be] = 'be'
function nhomTheoTen(ten) {
    var t = (ten || '').toLowerCase()
    if (!t) return null
    if (t.indexOf('nhac') >= 0 || t.indexOf('beat') >= 0 || t.indexOf('music') >= 0) return 'nhac'
    if (t.indexOf('mic') >= 0 || t.indexOf('giong') >= 0 || t.indexOf('voc') >= 0) return 'mic'
    if (t.indexOf('vang') >= 0 || t.indexOf('delay') >= 0 || t.indexOf('reverb') >= 0 || t.indexOf('echo') >= 0) return 'vang'
    if (t === 'be' || t.indexOf('be ') === 0 || t.indexOf('backing') >= 0) return 'be'
    return null
}

var kenh = []
var kenhInfo = []          // {nhom, fader, mute, giaTri, daDat, lech}
function cacKenhCuaNhom(nhom) {
    var ds = []
    for (var i = 0; i < kenhInfo.length; i++) if (kenhInfo[i].nhom === nhom) ds.push(i)
    return ds
}
for (var i = 0; i < SO_KENH_THEO_DOI; i++) {
    (function (idx) {
        var ch = bankZone.makeMixerBankChannel()
        kenh.push(ch)
        var info = {
            nhom: nhomTheoChiSo.hasOwnProperty(idx) ? nhomTheoChiSo[idx] : null,
            fader: surface.makeCustomValueVariable('qlk_fader_' + idx),
            mute: surface.makeCustomValueVariable('qlk_mute_' + idx),
            giaTri: 0, daDat: -1, lech: 0
        }
        kenhInfo.push(info)
        page.makeValueBinding(info.fader, ch.mValue.mVolume)
        page.makeValueBinding(info.mute, ch.mValue.mMute)

        // Ten kenh doi = bai da nap toi muc mixer co track. Day la tin hieu "san sang".
        ch.mValue.mVolume.mOnTitleChange = function (activeDevice, activeMapping, objectTitle, valueTitle) {
            var len = objectTitle ? objectTitle.length : 0
            var nhom = nhomTheoTen(objectTitle)
            if (len > 0) {
                if (!nhom && nhomTheoChiSo.hasOwnProperty(idx)) nhom = nhomTheoChiSo[idx]
                log('kenh[' + idx + '] ten="' + objectTitle + '" nhom=' + (nhom || '-'))
            } else {
                nhom = null
            }
            info.nhom = nhom
            guiCC(activeDevice, CC_TEN_KENH_GOC + idx, len)
        }
        ch.mValue.mVolume.mOnProcessValueChange = function (activeDevice, activeMapping, value) {
            info.giaTri = value
            if (!info.nhom) return
            var ds = cacKenhCuaNhom(info.nhom)
            if (ds[0] === idx) guiCC(activeDevice, faderCCTheoNhom[info.nhom], value * 127)
            if (ds.length > 1 && Math.abs(value - info.daDat) > 0.003) doLech(info.nhom)   // keo tay trong Cubase
        }
        ch.mValue.mVolume.mOnDisplayValueChange = function (activeDevice, activeMapping, value, units) {
            if (idx === KENH.mic) log('fader Mic hien thi "' + value + ' ' + units + '"')
        }
        ch.mValue.mMute.mOnProcessValueChange = function (activeDevice, activeMapping, value) {
            if (info.nhom && cacKenhCuaNhom(info.nhom)[0] === idx) guiCC(activeDevice, muteCCTheoNhom[info.nhom], value > 0.5 ? 127 : 0)
        }
    })(i)
}
function doLech(nhom) {
    var ds = cacKenhCuaNhom(nhom)
    for (var j = 0; j < ds.length; j++) kenhInfo[ds[j]].lech = kenhInfo[ds[j]].giaTri - kenhInfo[ds[0]].giaTri
}
function datFaderNhom(activeDevice, nhom, value) {
    var ds = cacKenhCuaNhom(nhom)
    for (var j = 0; j < ds.length; j++) {
        var kk = kenhInfo[ds[j]]
        var v = j === 0 ? value : value + kk.lech
        if (v < 0) v = 0
        if (v > 1) v = 1
        kk.daDat = v
        kk.fader.setProcessValue(activeDevice, v)
    }
}
function datMuteNhom(activeDevice, nhom, value) {
    var ds = cacKenhCuaNhom(nhom)
    for (var j = 0; j < ds.length; j++) kenhInfo[ds[j]].mute.setProcessValue(activeDevice, value)
}
for (var ni = 0; ni < NHOM.length; ni++) {
    (function (nhom) {
        var kFader = knobCC(faderCCTheoNhom[nhom])
        kFader.mSurfaceValue.mOnProcessValueChange = function (activeDevice, value, diff) {
            datFaderNhom(activeDevice, nhom, value)
        }
        var bMute = buttonCC(muteCCTheoNhom[nhom])
        bMute.mSurfaceValue.mOnProcessValueChange = function (activeDevice, value, diff) {
            datMuteNhom(activeDevice, nhom, value)
        }
    })(NHOM[ni])
}

// ---- 4. Plugin o insert slot kenh Mic: tham so theo CHI SO (API Cubase 13.0) ----------------
// Cubase 13.0.10 KHONG co DirectAccess/accessSlotAtIndex (xem .api/v1/midiremote_api_v1.d.ts).
// Chi co: makeInsertEffectViewer().excludeEmptySlots() -> viewer tro vao slot co plugin dau tien,
// va mParameterBankZone.makeParameterValue() lay tham so theo thu tu cua plugin (Remote Control Editor).
// Cach lam: tao SO_THAM_SO gia tri, bind moi gia tri vao mot knob CC (CC_THAM_SO_GOC + i).
//   -> app gui CC 80+i de dat tham so i (0..127 ~ 0..1). Ten/gia tri hien thi gui ve bang SysEx
//      (loai 1: param|i|ten, loai 4: disp|i|gia_tri|don_vi), app tu tim chi so cua "Key"/"Scale".
// Tham so 0..47: CC 80..127 kenh 0 (app/thamdo dat duoc). Tham so 48..: chi THEO DOI (ten + gia tri
// hien thi ra console/SysEx) qua CC gia tren kenh MIDI 1.. (Auto-Tune Pro co hon 100 tham so, scale GUI nam sau 32).
var SO_THAM_SO = 200
var CC_THAM_SO_GOC = 80          // CC 80..127
var SO_THAM_SO_CC_THAT = 128 - CC_THAM_SO_GOC
function knobCCKenh(channel, cc) {
    var k = surface.makeKnob(_x, 4, 1, 1)
    _x += 1
    k.mSurfaceValue.mMidiBinding.setInputPort(midiInput).bindToControlChange(channel, cc)
    return k
}
function knobThamSo(i) {
    if (i < SO_THAM_SO_CC_THAT) return knobCC(CC_THAM_SO_GOC + i)
    var j = i - SO_THAM_SO_CC_THAT
    return knobCCKenh(1 + Math.floor(j / 100), j % 100)
}
var insertViewer = kenh[KENH.mic].mInsertAndStripEffects.makeInsertEffectViewer('QuangLuuInsertMic').excludeEmptySlots()
var thamSo = []
for (var pi = 0; pi < SO_THAM_SO; pi++) {
    (function (i) {
        var pv = insertViewer.mParameterBankZone.makeParameterValue()
        var k = knobThamSo(i)
        page.makeValueBinding(k.mSurfaceValue, pv)
        pv.mOnTitleChange = function (activeDevice, activeMapping, objectTitle, valueTitle) {
            if (objectTitle && objectTitle.length) {
                log('param[' + i + '] "' + objectTitle + '" / "' + valueTitle + '"')
                guiSysEx(activeDevice, 0x01, 'param|' + i + '|' + objectTitle + '|' + valueTitle)
                // objectTitle = TEN PLUGIN, valueTitle = TEN THAM SO (do 2026-10-07: log in 'param[2] "Auto-Tune Pro" / "Key"').
                // Tham so ten "Key" o chi so i -> chon ho so plugin co key_root = i (du phong khi
                // mOnChangePluginIdentity khong chay; Cubase 15 thi identity van chay sau Reload Scripts).
                if (valueTitle === 'Key') chonHoSoTheoChiSoKey(i)
            }
        }
        pv.mOnDisplayValueChange = function (activeDevice, activeMapping, value, units) {
            log('disp[' + i + '] ' + value + ' ' + units)
            guiSysEx(activeDevice, 0x04, 'disp|' + i + '|' + value + '|' + units)
        }
        thamSo.push(pv)
    })(pi)
}
// App gui key_root (CC 33), scale_type (CC 35), tone_auto (CC 40) nhu voi Studio One.
// Chi so tham so KHAC NHAU theo plugin (doc tu bang param|i|ten qua SysEx / Script Console):
//   Steinberg Pitch Correct (Cubase 13.0.10, do 2026-10-04): 6 Key, 7 Scale, 3 PitchCorrect (Off/2..100)
//   Antares Auto-Tune Pro 11.0.0 VST3 (may khach, do 2026-10-06): 2 Key, **162 "Modern Scale"** (Scale tren GUI:
//       Chromatic/Major/Minor/Harmonic Minor/...). Tham so 1 "Scale" la bang scale co dien (Major/Minor/Chromatic/
//       Ling Lun/...) KHONG dieu khien GUI che do Modern. 0 Correction Mode, 3 Detune, 4 Retune Speed, 5-7 Vibrato,
//       8 Re-Track ARA, 9 Tracking, 10 Input Type. Khong lo tham so bat/tat -> tone_auto = -1: nut On cua insert slot.
// Cach gan: moi ho so co bo bien rieng (makeCustomValueVariable) bind thang vao tham so cua no;
// knob CC cua app KHONG bind host, chi chuyen gia tri sang bien cua ho so dang chon (JS thuan).
// Khong dung sub page: mActivate.trigger() goi tu callback khong doi binding (do 2026-10-06).
// Ho so chon theo ten tham so "Key" (chay ca khi Reload Scripts) va theo mOnChangePluginIdentity.
// be (CC 47, nut Be cua app, 127 = bat): Harmony Player cua Auto-Tune Pro 11. Do tren may khach DESKTOP-826077C
// 2026-10-07 (Cubase 15, Auto-Tune Pro 11.0.0 VST3): tham so **155 "HP Bypass Harmony Player"** (On = tat be) ->
// be_la_bypass: true de dao chieu (app 127 = bat be -> bypass 0). Cac tham so HP khac: 115-118 Voice 1-4 Fixed Interval,
// 119-122 Scale Interval, 123-127 Latch, 128-131 Level, 132-135 Pan, 136-139 Width, 140-143 Formant, 144-147 Solo,
// 148-152 Trigger, 153 Interval Type, 155 Bypass HP, 156 Mute Input, 157 Solo Input, 158 Naturalize, 159-160 Variation,
// 161 Transition Time, 163-164 Attack/Release, 165-172 EQ, 173-174 Gate, 175 Stereo Width, 176-178 Bypass Gate/Env/EQ,
// 180 Mixer Show/Hide, 187 "Key" (cua HP, khong phai Key chinh = 2). Plugin khong co bo be thi -1 = chi log.
// scale_dorian / scale_chromatic: gia tri MIDI (0..127) dua vao tham so scale_type khi bat mode
// Dan Ca (CC 46) / Fix Meo (CC 45); -1 = plugin chua do, chi ghi log. (Phan nay lay tu ban script tren may khach
// DESKTOP-826077C, 2026-10-07 16:57, do phien Claude rieng cua khach viet.)
//   Auto-Tune Pro 11 "Modern Scale" (may khach, do 2026-10-07 bang Can chinh trong app):
//   Chromatic 0-5, Major 6-13, Minor 14-22, Harmonic Minor 23-31, Jazz Melodic Minor 32-40, Dorian 41-49.
// scale_classic: tham so "Scale" bang co dien cua Auto-Tune Pro (1; 186 la ban sao). May khach DESKTOP-M21N7VP (2026-10-08) GUI/am thanh
// di theo tham so NAY chu khong theo 162 "Modern Scale" (may 1, 2 thi nguoc lai) -> khi nhan CC 35 script ghi CA HAI:
// 162 = gia tri app, 1 = quy doi tu bang Modern sang bang co dien (Chromatic 0-5 -> 10, Major 6-13 -> 1, Minor 14-22 -> 5;
// scale khac khong co trong bang co dien thi de nguyen). Bang co dien do tren may 3: Major 0-2, Minor 3-7, Chromatic 8-11.
// Ban Auto-Tune Pro tren may 3 (file .vst3 2024-04-06) chi co bang co dien tren GUI, ca o Modern lan Classic (tham so 11):
// quet CC 81 (2026-10-08): Major, Minor, Chromatic, Ling Lun, Scholar's Lute, Greek..., Just, Barnes-Bach, Pelog, Arabic, 24 Tone,
// Partch, Harmonic = 29 scale lich su, KHONG co Dorian; tham so 162 doi duoc gia tri host nhung GUI khong theo. Vi vay Dan Ca
// (Dorian) tren bang co dien lui ve Minor (gan Dorian nhat: chi khac bac 6) - scaleCoDienTuModern(41..49) = 5. Chromatic (Fix Meo)
// co trong bang co dien nen ghi dung. Tat/bat Classic Mode khong giup gi (da thu), script KHONG dung den tham so 11.
var HO_SO_PLUGIN = [
    { ten: 'Pitch Correct', key_root: 6, scale_type: 7, tone_auto: 3, be: -1, scale_dorian: -1, scale_chromatic: -1, scale_classic: -1 },
    { ten: 'Auto-Tune Pro', key_root: 2, scale_type: 162, tone_auto: -1, be: 155, be_la_bypass: 1, scale_dorian: 45, scale_chromatic: 2, scale_classic: 1,
      // App gui Scale theo bang Pitch Correct cua ho so DAW cubase (Major 22-63 tam 43, Minor 64-105 tam 85). Tren Modern Scale
      // cua Auto-Tune 43 lai la Dorian, 85 ngoai bang -> quy doi tai day: [tu, den, gia tri Auto-Tune]. Gia tri 0-22 (bang Auto-Tune: da can chinh
      // bang app: Major 10 / Minor 18, hoac Chromatic) di thang. Nho vay may khach KHONG can calibration_overrides.json nua.
      scale_tu_pitch_correct: [[23, 63, 10], [64, 105, 18]] }
]
function scaleTheoHoSo(value) {        // value 0..1 app gui -> 0..1 theo bang cua plugin dang chon
    var bang = hoSoHienTai.scale_tu_pitch_correct
    if (!bang) return value
    var cc = Math.round(value * 127)
    for (var i = 0; i < bang.length; i++) if (cc >= bang[i][0] && cc <= bang[i][1]) return bang[i][2] / 127
    return value
}
function scaleCoDienTuModern(cc) {      // cc 0..127 cua bang Modern -> cc bang co dien, -1 = khong quy doi duoc
    if (cc <= 5) return 10                  // Chromatic
    if (cc <= 13) return 1                  // Major
    if (cc <= 22) return 5                  // Minor
    if (cc >= 41 && cc <= 49) return 5      // Dorian -> Minor (bang co dien khong co Dorian)
    return -1
}
var ccTheoKhoa = { key_root: CC.key_root, scale_type: CC.scale_type, tone_auto: CC.tone_auto, be: CC.be }
var hoSoHienTai = HO_SO_PLUGIN[0]
for (var hi = 0; hi < HO_SO_PLUGIN.length; hi++) {
    (function (hoSo, so) {
        hoSo.bien = {}
        for (var khoa in ccTheoKhoa) {
            if (!ccTheoKhoa.hasOwnProperty(khoa)) continue
            var idx = hoSo[khoa]
            var bien = null
            if (idx >= 0) {
                bien = surface.makeCustomValueVariable('ql_' + so + '_' + khoa)
                page.makeValueBinding(bien, thamSo[idx])
            } else if (khoa === 'tone_auto') {
                // Plugin khong lo tham so bat/tat -> nut On cua insert slot.
                bien = surface.makeCustomValueVariable('ql_' + so + '_' + khoa)
                page.makeValueBinding(bien, insertViewer.mOn)
            }
            hoSo.bien[khoa] = bien
        }
        hoSo.bien.scale_classic = null
        if (hoSo.scale_classic >= 0) {
            hoSo.bien.scale_classic = surface.makeCustomValueVariable('ql_' + so + '_scale_classic')
            page.makeValueBinding(hoSo.bien.scale_classic, thamSo[hoSo.scale_classic])
        }
    })(HO_SO_PLUGIN[hi], hi)
}
// Mode ghi de Scale: Fix Meo (CC 45) -> Chromatic, Dan Ca (CC 46) -> Dorian. Fix Meo uu tien hon.
// Scale app gui (CC 35) luc mode dang bat duoc nho lai, tat mode thi tra ve scale do.
var scaleApp = -1            // gia tri chuan hoa 0..1 cua CC 35 gan nhat (-1 = chua nhan)
var modeScale = { fix_meo: false, mode_danca: false }
function datScale(activeDevice, value, lyDo) {   // value 0..1 theo bang Modern; ghi 162 va quy doi sang bang co dien (1)
    hoSoHienTai.bien.scale_type.setProcessValue(activeDevice, value)
    var bc = hoSoHienTai.bien.scale_classic
    var cd = bc ? scaleCoDienTuModern(Math.round(value * 127)) : 0
    if (bc && cd >= 0) bc.setProcessValue(activeDevice, cd / 127)
    if (lyDo) log('scale -> ' + lyDo + (bc && cd === 5 && value * 127 > 40 ? ' (bang co dien: Minor)' : ''))
}
function apScale(activeDevice) {
    var bien = hoSoHienTai.bien.scale_type
    if (!bien) return
    if (modeScale.fix_meo && hoSoHienTai.scale_chromatic >= 0) {
        datScale(activeDevice, hoSoHienTai.scale_chromatic / 127, 'Chromatic (Fix Meo)')
    } else if (modeScale.mode_danca && hoSoHienTai.scale_dorian >= 0) {
        datScale(activeDevice, hoSoHienTai.scale_dorian / 127, 'Dorian (Dan Ca)')
    } else if (scaleApp >= 0) {
        datScale(activeDevice, scaleTheoHoSo(scaleApp), null)
    } else if (modeScale.fix_meo || modeScale.mode_danca) {
        log('mode bat nhung ' + hoSoHienTai.ten + ' chua co gia tri Chromatic/Dorian')
    }
}
for (var khoa in ccTheoKhoa) {
    if (!ccTheoKhoa.hasOwnProperty(khoa)) continue
    (function (k) {
        var knob = knobCC(ccTheoKhoa[k])
        knob.mSurfaceValue.mOnProcessValueChange = function (activeDevice, value, diff) {
            if (k === 'scale_type') { scaleApp = value; apScale(activeDevice); return }
            if (k === 'be' && hoSoHienTai.be_la_bypass) value = 1 - value   // tham so la Bypass: bat be = bypass 0
            var bien = hoSoHienTai.bien[k]
            if (bien) bien.setProcessValue(activeDevice, value)
            else log('nhan CC ' + ccTheoKhoa[k] + ' = ' + Math.round(value * 127) + ' (' + k + ' chua gan tren ' + hoSoHienTai.ten + ')')
        }
    })(khoa)
}
for (var mk in modeScale) {
    if (!modeScale.hasOwnProperty(mk)) continue
    (function (m) {
        var knob = knobCC(CC[m])
        knob.mSurfaceValue.mOnProcessValueChange = function (activeDevice, value, diff) {
            modeScale[m] = value > 0.5
            log('nhan CC ' + CC[m] + ' = ' + Math.round(value * 127) + ' (' + m + (modeScale[m] ? ' BAT' : ' TAT') + ')')
            apScale(activeDevice)
        }
    })(mk)
}
function datHoSo(hoSo, lyDo) {
    if (hoSoHienTai !== hoSo) log('ho so plugin: ' + hoSo.ten + ' (' + lyDo + ')')
    hoSoHienTai = hoSo
}
function chonHoSoTheoChiSoKey(idx) {
    for (var i = 0; i < HO_SO_PLUGIN.length; i++) {
        if (HO_SO_PLUGIN[i].key_root === idx) { datHoSo(HO_SO_PLUGIN[i], 'Key o tham so ' + idx); return }
    }
    log('tham so "Key" o chi so ' + idx + ' chua co ho so')
}
function chonHoSoPlugin(pluginName) {
    for (var i = 0; i < HO_SO_PLUGIN.length; i++) {
        if (pluginName && pluginName.indexOf(HO_SO_PLUGIN[i].ten) === 0) { datHoSo(HO_SO_PLUGIN[i], 'ten plugin'); return }
    }
    log('plugin "' + pluginName + '" chua co ho so, giu ' + hoSoHienTai.ten)
}
insertViewer.mOnChangePluginIdentity = function (activeDevice, activeMapping, pluginName, pluginVendor, pluginVersion, formatVersion) {
    log('plugin "' + pluginName + '" (' + pluginVendor + ' ' + pluginVersion + '/' + formatVersion + ')')
    guiSysEx(activeDevice, 0x02, 'plugin|' + pluginName + '|' + pluginVendor + '|' + pluginVersion)
    guiCC(activeDevice, CC_PLUGIN, 1)
    chonHoSoPlugin(pluginName)
}
insertViewer.mOnTitleChange = function (activeDevice, activeMapping, title) {
    log('insert viewer title "' + title + '"')
    guiSysEx(activeDevice, 0x05, 'viewer|' + title)
}

// ---- 6. Plugin o insert slot kenh Nhac (pitch shift: Waves SoundShifter Pitch Stereo tren may khach) ----
// App gui tone_music (CC 10, Tone Nhac) va tone_voice (CC 11, Tone Giong): 0..127 = -12..+12 ban cung
// (frontend_qt._set_tone_offset: cc = (st + 12) / 24 * 127, 0 ban cung = CC 63).
// Tone Nhac dich ca nhac nen app DONG THOI gui key_root (CC 33) da dich theo -> Auto-Tune Key doi theo (muc 4);
// script chi can dua Tone Nhac vao tham so ban cung cua plugin pitch tren kenh Nhac.
// May khach chi co MOT plugin pitch (tren NHAC) nen ca hai nut cung vao do: ban cung plugin = Tone Nhac + Tone Giong
// (cong roi kep -12..+12) de nut nay khong ghi de nut kia khi app gui lai ca hai luc khoi phuc bai.
// Waves SoundShifter Pitch Stereo (may khach, do 2026-10-07): tham so 4 "PitchSemitones" (0 .. 9, bank lap chu ky 10),
// gia tri 0..1 = -12..+12 ban cung tuyen tinh (kiem +-12 dat).
var SO_THAM_SO_NHAC = 16   // SoundShifter chi co 10 tham so, bank lap lai theo chu ky 10
var KENH_MIDI_NHAC = 3
var viewerNhac = kenh[KENH.nhac].mInsertAndStripEffects.makeInsertEffectViewer('QuangLuuInsertNhac').excludeEmptySlots()
var thamSoNhac = []
for (var pn = 0; pn < SO_THAM_SO_NHAC; pn++) {
    (function (i) {
        var pv = viewerNhac.mParameterBankZone.makeParameterValue()
        var k = knobCCKenh(KENH_MIDI_NHAC + Math.floor(i / 100), i % 100)
        page.makeValueBinding(k.mSurfaceValue, pv)
        pv.mOnTitleChange = function (activeDevice, activeMapping, objectTitle, valueTitle) {
            if (objectTitle && objectTitle.length) {
                log('nhac param[' + i + '] "' + objectTitle + '" / "' + valueTitle + '"')
                guiSysEx(activeDevice, 0x06, 'nparam|' + i + '|' + objectTitle + '|' + valueTitle)
            }
        }
        pv.mOnDisplayValueChange = function (activeDevice, activeMapping, value, units) {
            log('nhac disp[' + i + '] ' + value + ' ' + units)
            guiSysEx(activeDevice, 0x07, 'ndisp|' + i + '|' + value + '|' + units)
        }
        thamSoNhac.push(pv)
    })(pn)
}
// Ho so plugin pitch kenh Nhac: ban_cung = chi so tham so dich ban cung (-1 = chua gan).
var HO_SO_NHAC = [
    { ten: 'SoundShifter', ban_cung: 4 }
]
var hoSoNhacHienTai = HO_SO_NHAC[0]
for (var hn = 0; hn < HO_SO_NHAC.length; hn++) {
    (function (hoSo, so) {
        hoSo.bien = null
        if (hoSo.ban_cung < 0) return
        hoSo.bien = surface.makeCustomValueVariable('qln_' + so + '_ban_cung')
        page.makeValueBinding(hoSo.bien, thamSoNhac[hoSo.ban_cung])
    })(HO_SO_NHAC[hn], hn)
}
var ccTheoKhoaNhac = { tone_music: CC.tone_music, tone_voice: CC.tone_voice }
// May khach (DESKTOP-U46KFB8, do 2026-10-07): app_config.json cua khach dat tone_music = 55 (ky thuat vien doi
// tu hoi thanh "Giong" con gui nham CC 10). Script nghe them CC 55 nhu Tone Nhac de khong phai sua config khach.
var CC_TONE_MUSIC_KHACH = 55
var toneApp = { tone_music: 0, tone_voice: 0 }      // ban cung app dang gui, theo tung nut
function banCungTuCC(value) {                        // value 0..1 (= CC/127) -> -12..+12
    var st = Math.round(value * 24 - 12)
    if (st < -12) st = -12
    if (st > 12) st = 12
    return st
}
function datBanCungNhac(activeDevice, nguon) {
    var tong = toneApp.tone_music + toneApp.tone_voice
    if (tong < -12) tong = -12
    if (tong > 12) tong = 12
    var moTa = 'Tone Nhac ' + toneApp.tone_music + ' + Tone Giong ' + toneApp.tone_voice + ' = ' + tong + ' ban cung (' + nguon + ')'
    if (!hoSoNhacHienTai.bien) { log(moTa + ' - chua gan tren ' + hoSoNhacHienTai.ten); return }
    hoSoNhacHienTai.bien.setProcessValue(activeDevice, (tong + 12) / 24)
    log(moTa + ' -> ' + hoSoNhacHienTai.ten)
}
var ccToneNhac = [
    { khoa: 'tone_music', cc: ccTheoKhoaNhac.tone_music },
    { khoa: 'tone_music', cc: CC_TONE_MUSIC_KHACH },
    { khoa: 'tone_voice', cc: ccTheoKhoaNhac.tone_voice }
]
for (var ti = 0; ti < ccToneNhac.length; ti++) {
    (function (k, cc) {
        var knob = knobCC(cc)
        knob.mSurfaceValue.mOnProcessValueChange = function (activeDevice, value, diff) {
            toneApp[k] = banCungTuCC(value)
            datBanCungNhac(activeDevice, k + ' CC ' + cc)
        }
    })(ccToneNhac[ti].khoa, ccToneNhac[ti].cc)
}
viewerNhac.mOnChangePluginIdentity = function (activeDevice, activeMapping, pluginName, pluginVendor, pluginVersion, formatVersion) {
    log('plugin Nhac "' + pluginName + '" (' + pluginVendor + ' ' + pluginVersion + ')')
    for (var i = 0; i < HO_SO_NHAC.length; i++) {
        if (pluginName && pluginName.indexOf(HO_SO_NHAC[i].ten) === 0) { hoSoNhacHienTai = HO_SO_NHAC[i]; return }
    }
    log('plugin Nhac "' + pluginName + '" chua co ho so')
}

// Cac CC con lai cua app: chi ghi log de biet Cubase CO nhan duoc (gan vao dau la viec cua giai doan 2).
var ccChiLog = [CC.tat_on, 30, 31, 32, 34, 36, 37, 38, 39, 41, 42, 43, 44, 54]
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
    log('driver active: Cubase da thay QuangLuuMIDI + QLS_PhanHoi (script ' + QLS_SCRIPT_VERSION + ')')
    guiCC(activeDevice, 72, 1)
}
deviceDriver.mOnDeactivate = function (activeDevice) {
    log('driver inactive')
}
