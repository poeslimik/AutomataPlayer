# AutomataPlayer

MuseScore 악보를 게임 악기의 글쇠로 연주합니다. 포커스된 창에 키보드 입력만 보냅니다.

MuseScoreの楽譜を、ゲーム内の楽器キーで演奏します。前面のウィンドウにキーボード入力だけ送ります。

用游戏乐器的按键演奏 MuseScore 乐谱。只向当前窗口发送键盘输入。

Play MuseScore scores on in-game instrument keys. Only keyboard input is sent to the focused window.

```
.mscz / .mscx → Score → instrument keys → press/release → input backend
```

## 준비 / Setup

Python 3.10 이상이 필요합니다. 악보를 읽고 미리 보는 데는 추가 라이브러리가 필요 없습니다. Windows 외에서 실제로 키를 보내려면 `pip install -e ".[input]"` 후 `--backend pynput` 또는 `--backend auto`를 씁니다.

Python 3.10 以上が必要です。楽譜の読み込みとプレビューに追加ライブラリは要りません。Windows 以外で実際にキーを送るには `pip install -e ".[input]"` のあと `--backend pynput` または `--backend auto` を使います。

需要 Python 3.10 或更高版本。读取乐谱和预览不需要额外库。在 Windows 以外实际发送按键时，先执行 `pip install -e ".[input]"`，再使用 `--backend pynput` 或 `--backend auto`。

Python 3.10 or newer is required. Reading a score and previewing it needs no extra libraries. To send real keystrokes outside Windows, run `pip install -e ".[input]"` and use `--backend pynput` or `--backend auto`.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

## 실행 / Run

`dist\AutomataPlayer.exe`를 더블클릭합니다. 사용자 계정 컨트롤에서 **예**를 누르면 관리자 권한으로 창이 열립니다. 게임이 관리자 권한이면 이 프로그램도 같은 권한이어야 키가 닿습니다.

`dist\AutomataPlayer.exe` をダブルクリックします。ユーザーアカウント制御で **はい** を選ぶと、管理者として開きます。ゲームが管理者なら、このプログラムも同じ権限が必要です。

双击 `dist\AutomataPlayer.exe`。在用户账户控制中选 **是** 后，窗口会以管理员身份打开。如果游戏以管理员身份运行，本程序也需要相同权限。

Double-click `dist\AutomataPlayer.exe`. Choose **Yes** at the User Account Control prompt to open it as administrator. If the game is elevated, this program needs the same permission.

실행 파일은 [Releases](https://github.com/poeslimik/AutomataPlayer/releases)에서 `AutomataPlayer.exe`로 받을 수 있습니다. 새 버전 태그를 올리면 그 페이지에 자동으로 붙습니다.

実行ファイルは [Releases](https://github.com/poeslimik/AutomataPlayer/releases) の `AutomataPlayer.exe` から入手できます。新しいバージョンタグを付けると、そのページに自動で追加されます。

可执行文件可以从 [Releases](https://github.com/poeslimik/AutomataPlayer/releases) 下载 `AutomataPlayer.exe`。推送新版本标签后，文件会自动出现在该页面。

Download `AutomataPlayer.exe` from [Releases](https://github.com/poeslimik/AutomataPlayer/releases). Pushing a new version tag attaches the file to that page automatically.

인자 없이 켜면 같은 창이 열립니다. `찾아보기`로 `.mscz` 또는 `.mscx`를 고르고 악기를 고른 뒤 `연주`를 누릅니다. `미리보기`는 글쇠를 누르지 않습니다. `게임 창에 키 입력`은 대기 동안 게임 창을 고른 뒤 글쇠를 보냅니다. `중지` 또는 F8로 멈춥니다. 오른쪽 위의 `언어`에서 한국어, 일본어, 중국어, 영어를 고릅니다. 기본값은 한국어이고, 고른 언어는 다음에도 유지됩니다.

引数なしで起動すると同じウィンドウが開きます。`参照` で `.mscz` または `.mscx` を選び、楽器を選んで `演奏` を押します。`プレビュー` はキーを押しません。`ゲームウィンドウにキー入力` は待機中にゲームウィンドウを選んでからキーを送ります。`停止` または F8 で止まります。右上の `言語` で日本語、韓国語、中国語、英語を選べます。初期値は韓国語で、選んだ言語は次回も残ります。

不带参数启动会打开同一个窗口。用 `浏览` 选择 `.mscz` 或 `.mscx`，选好乐器后按 `演奏`。`预览` 不按键。`向游戏窗口发送按键` 会在等待期间选中游戏窗口再发送。用 `停止` 或 F8 停止。右上角 `语言` 可选中文、韩语、日语、英语。默认是韩语，选择会保留到下次。

Starting with no arguments opens the same window. Use `Browse` to choose a `.mscz` or `.mscx` file, pick an instrument, and press `Play`. `Preview` does not press keys. `Send keys to the game window` waits while you focus the game, then sends keys. Stop with `Stop` or F8. The `Language` control at the top right offers English, Korean, Japanese, and Chinese. The default is Korean, and the choice is kept for the next launch.

```powershell
python -m automata_player
python -m automata_player instruments
python -m automata_player inspect examples\c_major_scale.mscx
python -m automata_player play examples\c_major_scale.mscx --instrument genshin-lyre
python -m automata_player play song.mscz --instrument nte-piano --backend windows
```

기본 백엔드는 `dry-run`입니다. 글쇠를 누르지 않고 시각과 키만 출력합니다. 명령줄 문장은 한국어입니다.

既定のバックエンドは `dry-run` です。キーは押さず、時刻とキーだけを出します。コマンドの表示文は韓国語です。

默认后端是 `dry-run`。不按键，只输出时间和按键。命令行文字是韩语。

The default backend is `dry-run`. It prints times and keys without pressing them. Command-line text is Korean.

```
악보: C major scale
악기: 바람의 노래 하프 (genshin-lyre)
음표: 8개, 길이 4.00초, 배속 1
시각(초)  동작  키      음
   0.000  누름  a       C4
   0.050  뗌    a       C4
미리보기 끝. 키 동작 16개.
```

실제 입력은 카운트다운 동안 게임 창을 고릅니다. 입력기는 영문으로 둡니다. 터미널에서는 Ctrl+C로도 멈춥니다.

実際の入力では、カウントダウン中にゲームウィンドウを選びます。入力言語は英語にします。ターミナルでは Ctrl+C でも止まります。

实际输入时，在倒计时期间点选游戏窗口。输入法请用英文。终端里也可以用 Ctrl+C 停止。

For live input, focus the game during the countdown. Keep the input language on English. Ctrl+C also stops a terminal run.

| 옵션 / Option | 의미 / Meaning |
| --- | --- |
| `--instrument`, `-i` | `genshin-lyre`, `genshin-vintage-lyre`, `nte-piano`, `nte-guitar` |
| `--backend`, `-b` | `dry-run` (default), `windows`, `pynput`, `auto` |
| `--speed` | 1보다 크면 빨라집니다 / Faster above 1 / 大于 1 更快 / 1より大きいと速い |
| `--transpose` | 반음 단위. 옥타브는 12 / Semitones. An octave is 12 / 半音为单位，八度是 12 / 半音単位。オクターブは 12 |
| `--part` | 파트 번호(1부터) 또는 이름. 여러 번 지정 / Part number from 1, or name. Repeatable |
| `--countdown` | 실제 입력 전 대기 초. 기본 3 / Seconds before live input. Default 3 |
| `--realtime` | 미리보기도 박자대로 대기 / Preview waits in time |
| `--tap-ms` | 짧게 누르는 악기의 눌림 시간(ms) / Tap length in milliseconds |

## 악기 / Instruments

게임 안의 공식 이름을 씁니다. 영어 악기는 lyre이고, 한국어 클라이언트는 그것을 하프로 적습니다. 이환의 한국어 이름은 이환, 중국어는 异环, 일본어와 영어는 NTE(Neverness to Everness)입니다. 코드의 id는 `nte-`로 통일합니다.

ゲーム内の正式名称を使います。英語の楽器名は lyre で、韓国語クライアントはこれを하프と表記します。韓国語のゲーム名は이환、中国語は异环、日本語と英語は NTE（Neverness to Everness）です。コード上の id は `nte-` に揃えます。

使用游戏内的正式名称。英文乐器名是 lyre，韩文客户端把它写成하프。韩文游戏名是이환，中文是异环，日文和英文是 NTE（Neverness to Everness）。代码里的 id 统一用 `nte-`。

Names follow the in-game titles. The English instrument is a lyre; the Korean client writes that word as 하프. The Korean title of the game is 이환, the Chinese title is 异环, and Japanese and English use NTE (Neverness to Everness). Code ids stay on the `nte-` prefix.

| id | 한국어 | 日本語 | 中文 | English | 건반 / Keys | 입력 / Touch |
| --- | --- | --- | --- | --- | --- | --- |
| `genshin-lyre` | 바람의 노래 하프 | 風吹きのライアー | 风物之诗琴 | Windsong Lyre | C3–B5 자연음 21키 / 21 naturals | 50ms |
| `genshin-vintage-lyre` | 낡은 하프 | 古びたライアー | 老旧的诗琴 | Vintage Lyre | 낮은·가운데 C 도리안, 높은 C 프리기안 / low and middle C Dorian, high C Phrygian | 50ms |
| `nte-piano` | 이환 피아노 | NTE ピアノ | 异环钢琴 | NTE Piano | 화면 36키, 키보드 21키 / 36 keys on screen, 21 keyboard keys | 음 길이 / held |
| `nte-guitar` | 이환 기타 | NTE ギター | 异环吉他 | NTE Guitar | E3–D#6, 반음 36키 / 36 chromatic keys | 음 길이 / held |

바람의 노래 하프와 이환 피아노는 키보드에서 같은 21키를 씁니다. 이환 피아노 화면에는 36키가 표시됩니다. 21키 모드에서는 반음을 낼 수 없어 하프와 같아지고, 36키 연주에서는 Shift가 C·F·G를 반음 올리고 Ctrl이 E·B를 반음 내립니다.

風吹きのライアーと NTE ピアノは、キーボードでは同じ21鍵です。NTE ピアノの画面には36鍵が表示されます。21鍵モードでは半音が出せずライアーと同じになり、36鍵の演奏では Shift が C・F・G を半音上げ、Ctrl が E・B を半音下げます。

风物之诗琴和异环钢琴在键盘上使用同样的 21 个键。异环钢琴画面显示 36 个键。21 键模式不能演奏半音，因此与诗琴相同；36 键演奏时，Shift 把 C、F、G 升高半音，Ctrl 把 E、B 降低半音。

The Windsong Lyre and the NTE piano share the same 21 keyboard keys. The piano screen shows 36 keys. The 21-key mode cannot play accidentals, so it matches the lyre. In the 36-key performance, Shift raises C, F, and G, and Ctrl lowers E and B.

```
Q W E R T Y U   C5–B5
A S D F G H J   C4–B4
Z X C V B N M   C3–B3
```

낡은 하프, 古びたライアー, 老旧的诗琴, Vintage Lyre:

```
Q W E R T Y U   C  D♭ E♭ F  G  A♭ B♭
A S D F G H J   C  D  E♭ F  G  A  B♭
Z X C V B N M   C  D  E♭ F  G  A  B♭
```

하프와 낡은 하프는 적힌 음만 칩니다. 낼 수 없는 음이 있으면 연주하지 않고, 이조하면 칠 수 있을 때 그 이조를 적용할 수 있습니다. 이환 피아노는 A♭을 G♯으로 칩니다. 음역 밖은 옥타브로 접습니다. 한 순간에 Shift나 Ctrl이 서로 모순이면 연주하지 않습니다. 같은 글쇠가 이어지면 떼고 다시 누르기 전에 30ms를 둡니다. 기타도 음역 밖을 옥타브로 접습니다.

ライアーと古びたライアーは、書かれた音だけを弾きます。出せない音があると演奏せず、移調すれば弾けるときはその移調を適用できます。NTE ピアノは A♭ を G♯ として弾きます。音域の外はオクターブで折り返します。同じ瞬間に Shift か Ctrl が矛盾すると演奏しません。同じ鍵が続くときは、離して押し直す前に 30ms 置きます。ギターも音域の外をオクターブで折り返します。

诗琴和老旧的诗琴只演奏谱上的音。有不能演奏的音时不开始，若移调后可以演奏，则可以应用该移调。异环钢琴把 A♭ 当成 G♯。超出音域的音按八度折回。同一时刻 Shift 或 Ctrl 互相矛盾时不演奏。同一个键连续出现时，松开再按下之前留 30ms。吉他也会把超出音域的音按八度折回。

The lyres play only the written pitches. If a note cannot be played, playback does not start; when a transposition makes it playable, that transposition can be applied. The NTE piano plays A♭ as G♯. Notes outside the range are folded by octaves. Playback is refused when Shift or Ctrl would have to be both down and up at the same moment. When the same key is struck again while held, 30ms is left between the release and the new press. The guitar also folds notes outside its range.

이환 기타는 아카네 린의 피아노 건반 모드입니다. 한 줄이 반음 12개이고, 각 줄은 E로 시작해 D#에서 끝납니다.

NTE ギターは明音凛のピアノ鍵盤モードです。1段が12半音で、各段は E から始まり D# で終わります。

异环吉他是明音凛的钢琴键盘模式。每一排 12 个半音，从 E 开始，到 D# 结束。

The NTE guitar is Akane Rin's piano-keyboard mode. Each row has 12 semitones, starting on E and ending on D#.

```
1 2 3 4 5 6 7 8 9 0 - =    E5–D#6
q w e r t y u i o p [ ]    E4–D#5
a s d f g h j k l ; ' Enter    E3–D#4
```

## 악보 / Score

`.mscz`와 `.mscx`를 읽습니다. MusicXML과 MIDI는 읽지 않습니다.

- 음높이, 쉼표, 화음, 여러 성부와 파트, 박자표, 변박, 점음표, 한 겹의 잇단음표, 이음줄, 템포, 못갖춘마디
- 반복, 도돌이표, 마디 중간의 세뇨·Fine·코다·D.C.·D.S., 1번·2번 괄호, 케이던차
- 페르마타는 그 음을 늘리고 뒤를 늦춥니다. 구간 나누기 뒤에는 기본 3초를 쉽니다
- 앞꾸밈음은 박 위에서 본음의 절반까지 차지하고, 여러 개면 그 시간을 똑같이 나눕니다
- 짧은 꾸밈음은 본음 앞에서 납니다. 바로 앞 음이 붙어 있으면 그 음의 절반과 꾸밈음 길이 중 짧은 쪽을 앞 음 끝에서 가져옵니다
- 아르페지오는 64틱 간격입니다. 화음에 다 안 들어가면 간격을 3분의 2로 줄입니다. 120 BPM에서는 약 0.067초이고, 빠르기가 바뀌어도 그 시간 간격은 같습니다. 묶음줄만 있으면 아래에서 위로 칩니다
- 재생이 켜진 트릴은 본음과 적힌 간격의 윗음을 번갈아 칩니다. 간격을 바꾸지 않으면 조에 맞는 2도이고, 단2도는 반음, 장2도는 온음입니다. 보통 빠르기에서는 32분음표, 아주 빠르면 16분음표, 느리면 더 잘게 나눕니다. 재생이 꺼진 트릴은 본음만 칩니다
- 글리산도와 포르타멘토는 두 음 사이의 반음을 채웁니다

`.mscz` と `.mscx` を読みます。MusicXML と MIDI は読みません。

- 音高、休符、和音、複数の声部とパート、拍子、変拍子、付点、一重の連符、タイ、テンポ、アウフタクト
- 反復、ダ・カーポ、小節途中のセグノ・Fine・コーダ・D.C.・D.S.、1番・2番括弧、カデンツァ
- フェルマータはその音を延ばし、後も遅らせます。セクション区切りの後は標準で3秒休みます
- 前打音は拍の上で主音の半分までを使い、複数あるときはその時間を等分します
- 短い装飾音は主音の前に鳴ります。直前の音がくっついていれば、その音の半分と装飾音の長さのうち短い方を直前の音の終わりから取ります
- アルペジオは64ティック間隔です。和音に入りきらなければ間隔を3分の2に縮めます。120 BPMでは約0.067秒で、テンポが変わってもその時間間隔は同じです。括弧だけなら下から上へ弾きます
- 再生が有効なトリルは、主音と記された間隔の上の音を交互に鳴らします。間隔を変えないときは調の2度、短2度は半音、長2度は全音です。普通の速さでは32分音符、とても速いときは16分音符、遅いときはさらに細かく分けます。無効なトリルは主音だけを鳴らします
- グリッサンドとポルタメントは二つの音の間の半音を埋めます

读取 `.mscz` 和 `.mscx`。不读取 MusicXML 和 MIDI。

- 音高、休止符、和弦、多个声部和声部、拍号、变拍、附点、一层连音、延音线、速度、弱起
- 反复、回头记号、小节中间的 Segno、Fine、Coda、D.C.、D.S.、一房子和二房子、华彩
- 延长号拉长该音并顺延后面的音。分节线之后默认停 3 秒
- 长倚音在拍点上最多占用本音的一半，有多个时平分这段时间
- 短倚音在本音之前发声。若紧挨着前一个音，就从前一个音的末尾取走“该音的一半”和“倚音时值”里较短的那段
- 琶音间隔是 64 tick。和弦里放不下时把间隔缩到三分之二。120 BPM 时大约 0.067 秒，速度改变后这段时间间隔不变。只有括号时从低到高
- 播放打开的颤音交替本音和所写间隔的上方音。不改间隔时是调内二度，小二度是半音，大二度是全音。一般速度按三十二分音符，很快时按十六分音符，慢时更细。播放关闭的颤音只奏本音
- 滑音和滑奏会补上两个音之间的半音

`.mscz` and `.mscx` are read. MusicXML and MIDI are not.

- Pitch, rests, chords, multiple voices and parts, time signatures, meter changes, dotted notes, one level of tuplets, ties, tempo, and pickup measures
- Repeats, dal segno and da capo, a segno, Fine, coda, D.C., or D.S. in the middle of a measure, first and second endings, and cadenzas
- A fermata lengthens its note and delays what follows. A section break inserts a three-second pause
- An appoggiatura takes up to half of the main note on the beat, and several of them divide that time equally
- An acciaccatura sounds before the beat. When the previous note is adjacent, it takes the shorter of half that note and the grace note's written length from the end of the previous note
- An arpeggio uses a 64-tick gap, shrunk by two thirds when the chord cannot hold it. At 120 BPM that is about 0.067 seconds, and the time gap stays the same when the tempo changes. A bracket with no arrow rolls from low to high
- A trill with playback enabled alternates the written note with the upper note from its interval. The default is the key's second; a minor second is one semitone and a major second is a whole tone. At a moderate tempo the notes are 32nds, at a very fast tempo 16ths, and slower tempos use shorter notes. A muted trill plays only the written note
- Glissando and portamento fill in the semitones between the two written notes


## 확장 / Extension

새 악기는 `Instrument` 하나를 `_INSTRUMENTS`에 넣습니다. `sustains`가 거짓이면 하프처럼 짧게 누르고, 참이면 음표 길이만큼 누릅니다. 다른 악보 형식은 `Score`를 돌려주는 함수를 `load_score`에 연결합니다. 음표 시각은 4분음표 개수이고, 템포는 BPM입니다. MuseScore의 `<tempo>` 값(4분음표/초)은 로더가 BPM으로 바꿉니다. 다른 입력 장치는 `InputBackend`의 `press`, `release`, `release_all`을 구현하고 `open_backend`에 등록합니다.

新しい楽器は `Instrument` を一つ `_INSTRUMENTS` に追加します。`sustains` が偽ならライアーのように短く押し、真なら音符の長さだけ押します。別の楽譜形式は `Score` を返す関数を `load_score` に繋ぎます。音符の時刻は四分音符の数、テンポは BPM です。MuseScore の `<tempo>`（四分音符/秒）はローダーが BPM に変換します。別の入力装置は `InputBackend` の `press`、`release`、`release_all` を実装して `open_backend` に登録します。

新乐器是往 `_INSTRUMENTS` 里加一个 `Instrument`。`sustains` 为假时像诗琴一样短按，为真时按住音的时值。其他乐谱格式把返回 `Score` 的函数接到 `load_score`。音符时间是四分音符个数，速度是 BPM。MuseScore 的 `<tempo>`（四分音符/秒）由读取器换成 BPM。其他输入设备实现 `InputBackend` 的 `press`、`release`、`release_all`，并注册到 `open_backend`。

Add an instrument by putting one `Instrument` in `_INSTRUMENTS`. When `sustains` is false the key is tapped, as on the lyre; when it is true the key is held for the written length. Another score format is a function that returns a `Score` and is connected to `load_score`. Note time is a count of quarter notes, and tempo is BPM. MuseScore's `<tempo>` value, in quarters per second, is converted to BPM by the loader. Another input device implements `press`, `release`, and `release_all` on `InputBackend` and is registered in `open_backend`.

```python
Instrument(
    id="my-instrument",
    name="내 악기",
    detail="음역과 글쇠 설명",
    sustains=True,
    keys=(KeyBinding(60, "a"),),
    verified=True,
)
```

## 테스트 / Tests

```powershell
pytest
```

## 주의 / Notice

이 연주는 해당 게임의 이용 약관과 다를 수 있습니다. 계정 제재 가능성은 직접 확인한 뒤 사용하세요.

この演奏は各ゲームの利用規約に沿わないことがあります。アカウント制限の可能性は自分で確認してから使ってください。

这样演奏可能不符合相应游戏的使用条款。请自行确认账号处罚风险后再使用。

This performance may conflict with a game's terms of service. Check the risk of account penalties yourself before use.
