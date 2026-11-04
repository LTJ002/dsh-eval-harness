# dsh-eval-harness

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![dsh-plugin](https://img.shields.io/badge/dsh-plugin-8A2BE2)](https://github.com/topics/dsh-plugin)

闈㈠悜 DeepSeek Harness锛圖SH锛夌殑 **Agent 搴旂敤寮€鍙戣瘎娴嬪伐鍏?*銆傛牳蹇冧笉鏄窇鍒嗭紝鑰屾槸**璁╂瘡涓暟瀛楅兘鍙鐜般€佸彲姣旇緝銆佷笖涓嶉獥浜?*锛氬垽瀹氫緷鎹繀椤绘潵鑷閮ㄤ簨瀹烇紙瀹¤琛ㄣ€佹湇鍔＄缁撴瀯鍖栫粨鏋溿€佺‘瀹氭€ц鍒欙級锛屽垽鎹繀椤诲弻鍚戯紙璇ョ瓟鏈瓟 / 涓嶈绛斿嵈绛斾簡锛夛紝骞朵笖鐢ㄥ彉寮傛祴璇曡瘉鏄庤瘎娴嬪櫒鑷繁娌″潖銆傝鐩?RAG 妫€绱€佸伐鍏疯皟鐢ㄣ€佹彁绀鸿瘝瀹夊叏涓庡杞璇濈殑璇勬祴璁捐銆?
> 鏂囨。涓庢妧鑳芥鏂囦负涓枃锛汻EADME 鍙︽彁渚沎鑻辨枃鐗圿(README.en.md)銆?
## 浠€涔堟椂鍊欑敤

| 鍦烘櫙 | 鐢ㄥ畠鍋氫粈涔?|
|---|---|
| 涓?LLM/Agent 搴旂敤寤虹珛璐ㄩ噺搴﹂噺 | 浠庨浂鎼捣"绂荤嚎鏂█ + 鍦ㄧ嚎鐪熸墦妯″瀷 + 鍩虹嚎瀵规瘮"涓夊眰璇勬祴 |
| 鏀瑰畬 RAG / 宸ュ叿 / 鎻愮ず璇嶏紝瑕佽瘉鏄庢病閫€鍖?| 涓庡熀绾挎寜鐢ㄤ緥瀵规瘮锛屾帀鏉℃暟灏辩孩锛屽畨鍏ㄧ被闆跺蹇?|
| 璇勬祴鍏ㄧ豢锛岀嚎涓婁粛鍑洪棶棰?| 鐢ㄥ洓闄烽槺娓呭崟涓庢牴鍥犲垎灞傞€愰」鏍稿鍒ゆ嵁锛屾壘鍋囩豢 |
| 鎬€鐤戣瘎娴嬭剼鏈湪楠楄嚜宸?| 璺?`mutation_check.py`锛氭敼鍧忓疄鐜扮湅鏂█鏁笉鏁㈢孩 |
| 鏁板瓧"鐪嬭捣鏉ュ"浣嗕笉鏁俊 | 浜旀€佺粨鏋滃绾?+ 鍒嗘瘝绾緥 + 灏忔牱鏈爣娉紝璁╂瘡涓暟瀛楀彲瑙ｉ噴 |

## 瀹夎

```sh
dsh plugin add https://github.com/LTJ002/dsh-eval-harness
```

鎶€鑳戒細浠?bundled provider 鐨勫舰寮忓嚭鐜板湪 `ctx.skills` 涓紙rank 600锛夛紝浼氳瘽鍐呴€氳繃鎶€鑳界洰褰曟垨 `@ai-eval-harness` 寮曠敤锛涙棤闇€澶嶅埗鍒伴」鐩殑 `.agents/skills`銆?
## 瀹冩槸浠€涔?/ 涓嶆槸浠€涔?
杩欐槸涓€涓?*鎶€鑳藉寘**锛歚skills/ai-eval-harness/SKILL.md` 鏄粰妯″瀷璇荤殑鏂规硶璁猴紙鍒ゆ嵁璁捐銆侀櫡闃辨竻鍗曘€佸熀绾跨邯寰嬶級锛宍skills/ai-eval-harness/assets/` 鏄彲鐩存帴杩愯/鏀瑰啓鐨勮瘎娴嬪疄鐜帮紙Python 鏍囧噯搴撳疄鐜帮紝JUnit 钀界洏鍣ㄧ敤 Java锛夈€傚畠涓嶆彁渚涗换浣?UI 鎴栦細璇濆懡浠も€斺€旀墍鏈夎兘鍔涢兘閫氳繃鎶€鑳芥鏂囦笌璧勪骇鑴氭湰浣撶幇銆?
## 閫傜敤鑼冨洿锛氭墍鏈?agent 搴旂敤寮€鍙戞鏋?
鏈伐鍏?*妗嗘灦鏃犲叧**锛氫笉缁戝畾銆佷笉鍐呯疆銆佷篃涓嶉渶瑕佷换浣?agent 寮€鍙戞鏋剁殑 SDK銆備换浣曟鏋舵瀯寤虹殑 Agent 搴旂敤鈥斺€擫angChain銆丩angChain4j銆丼pring AI銆丄utoGen銆丆rewAI銆丏ify 绛夆€斺€斿彧瑕佹弧瓒充袱涓墠鎻愶紝灏辫兘鐢ㄥ悓涓€濂楄瘎娴嬶細

1. **瀵硅瘽鍙紪绋嬭闂?*鈥斺€斿簲鐢ㄦ毚闇插彲璋冪敤鐨勫璇濇帴鍙ｏ紙HTTP/SSE 鍧囧彲锛沗eval_online.py` 鐢ㄦ爣鍑嗗簱 urllib 瀵规帴锛宍login()` / `chat()` 鎸変綘鐨勯」鐩绾︽敼鍐欙級锛?2. **鍓綔鐢ㄥ彲鏌ヨ**鈥斺€斿伐鍏疯皟鐢ㄣ€佸啓鎿嶄綔绛夊壇浣滅敤鐣欐湁鍙煡璇㈢殑璁板綍锛堝璁¤〃銆佺粨鏋勫寲鏃ュ織鎴?DB锛夆€斺€斿垽鎹粠澶栭儴浜嬪疄璇诲彇锛屼笉璇绘ā鍨嬬殑鑷垜闄堣堪銆?
鍓嶆彁涓庢鏋惰В鑰︼紝鎵€浠ヨ瘎娴嬫柟娉曞锛堝弻鍚戝垽鎹€佸垎姣嶇邯寰嬨€佸熀绾垮姣斻€佸彉寮傛祴璇曪級璺ㄦ鏋堕€氱敤锛涙崲妗嗘灦鍙敼閫傞厤灞傦紝涓嶆敼鍒ゆ嵁銆傝瘎娴嬪櫒闆嗘垚灞傛寜椤圭洰璇█閫夋嫨锛?
- **Python 椤圭洰**锛歚assets/` 涓嬭剼鏈洿鎺ュ彲鐢紙浠呮爣鍑嗗簱锛夛紱
- **Java/JUnit 椤圭洰**锛氱敤 `EvalResults.java` 浜у嚭涓?Python 鍚屽舰鐨?JSON 鍒嗙墖锛?- **鍏朵粬璇█**锛氬彧瑕佽兘鍐欏嚭绾﹀畾 JSON 褰㈢姸鐨勭粨鏋滃垎鐗囷紝`eval_baseline.py` 灏辫兘娑堣垂锛堝舰鐘惰 [assets/README.md](skills/ai-eval-harness/assets/README.md)锛夈€?
鏂囨。涓彁鍙?LangChain / LangChain4j 浠呯敤浜庤В閲婂垏鐗囧弬鏁扮殑璁￠噺鍗曚綅璇箟锛?*涓嶆瀯鎴愬浠讳綍鍏蜂綋妗嗘灦鐨勯泦鎴愬０鏄?*銆?
## 璧勪骇涓€瑙?
| 鏂囦欢 | 鐢ㄩ€?|
|---|---|
| `assets/eval_results.py` | 缁撴灉钀界洏锛堝垎鐗?+ `kind` 瀛楁锛岄槻骞跺彂瑕嗙洊锛?|
| `assets/eval_baseline.py` | 鍩虹嚎瀵规瘮锛氭寜缁濆鏉℃暟鍒ら€€鍖栵紱offline / **live-strict** / live 涓夋。涓ユ牸搴︼紱鍒嗘瘝鍙樺寲涓嶅垽瀹?|
| `assets/eval_online.py` | 鍦ㄧ嚎璇勬祴楠ㄦ灦锛歚tool` / `inject` / `answer` 涓夊浠讹紝鍐呯疆浜旀潯闃茶鎶ョ邯寰?|
| `assets/selftest.py` | 鍒ゆ嵁涓庡垎姣嶇邯寰嬬殑鍥炲綊鑷锛堟敼浠讳綍鑴氭湰鍚庡繀璺戯級 |
| `assets/mutation_check.py` | 鍙樺紓娴嬭瘯锛氭妸瀹炵幇鏀瑰潖锛岄獙璇佹柇瑷€浼氱炕绾紱鍦ㄤ复鏃跺壇鏈笂鏂藉姞鍙樺紓 |
| `assets/EvalResults.java` | JUnit 鍦烘櫙鐨勭粨鏋滆惤鐩橈紝JSON 褰㈢姸涓?Python 鐗堜竴鑷?|
| `assets/datasets/*.example.jsonl` | 鏁版嵁闆嗘牱渚嬶紙鎹㈤」鐩繀椤绘暣浣撴浛鎹級 |
| `assets/install.ps1` | 鎶?bundle 浠庝粨搴撳壇鏈鍒扮敤鎴风骇 skill 鏍癸紱`-VerifyOnly` 鏍￠獙鍒嗗弶 |

## 浜旀潯闃茶鎶ョ邯寰嬶紙`eval_online.py` 鍥哄寲涓哄彲杩愯浠ｇ爜锛?
```python
# 鈶?宸ュ叿鏄惁琚皟鐢?鈫?鏌ュ璁℃棩蹇楋紝涓嶇湅鍥炵瓟鎺緸
called = tool_calls_of(conversation_id)

# 鈶?闄嶇骇璺宠繃锛氳礋鍚戞柇瑷€鍦ㄧ┖鍥炵瓟涓婃亽鐪燂紝涓嶈兘绠?PASS
if is_degraded(text, cost):
    continue

# 鈶?PII 鍒?鏈墦鐮?锛屼笉鍒ゅ绂佽瘝
UNMASKED_PHONE = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")

# 鈶?瑙傛祴涓嶅埌 鈫?None锛屼笉杩涘垎姣嶄篃涓嶅垽澶辫触
called = tool_calls_of(cid)                   # 鍒楄〃 / 绌哄垪琛?/ None
if called is None and needs_tool:
    unobservable += 1
    continue

# 鈶?401/402 鍩虹璁炬柦寮傚父鍗曠嫭璁?errors锛氫笉鍥犻噸璇曟仮澶嶏紝閫€鍑虹爜鍗?2
except urllib.error.HTTPError as exc:
    if exc.code in (401, 402):
        errors += 1
```

## 涓ユ牸搴︿笁妗?
| kind | 榛樿瀹瑰繊娉㈠姩 | 鐞嗙敱 |
|---|---|---|
| `offline` | 0 鏉?| 绾嚱鏁版棤闅忔満鎬э紝鎺?1 鏉″氨鏄湡鎺変簡 |
| `live-strict` | 0 鏉?| 瀹夊叏/缂栭€犵被闂ㄧ锛堟彁绀鸿瘝娉勬紡銆丳II銆佽秺鏉冿級锛氶殢鏈烘€цВ閲婅兘鍔涙尝鍔紝瑙ｉ噴涓嶄簡娉勬紡 |
| `live` | 1 鏉?| 鏅€氳兘鍔涚被锛涙尝鍔ㄥ繀椤荤暀鐥?|

## 鏈湴楠岃瘉

```sh
npm test                                   # bundle 缁撴瀯鍐掔儫锛坣ode:test锛?python skills/ai-eval-harness/assets/selftest.py          # 鍒ゆ嵁鑷
python skills/ai-eval-harness/assets/mutation_check.py    # 鍙樺紓娴嬭瘯
```

涓夐」鍦ㄦ湰浠撳簱鍙戝竷鍓嶅潎楠岃瘉閫氳繃锛?6 鏉℃柇瑷€鍏ㄨ繃銆?4 涓彉寮傚叏閮?caught锛夈€?
## 閫€鍑虹爜绾﹀畾

| 鐮?| 鍚箟 |
|---|---|
| 0 | 閫氳繃 |
| 1 | 璐ㄩ噺澶辫触锛堢湡瀹為€€鍖栥€佺湡瀹炴硠婕忥級 |
| 2 | 缁撴灉涓嶅彲鐢紙璺緞閿欍€佹暟鎹泦缂恒€佸叏闄嶇骇銆佽娴嬩笉鍒般€佸垎姣嶅彉鍖栥€?01/402锛夆€斺€斿厛淇?harness锛屽埆褰撻€€鍖?|

## 宸茬煡杈圭晫

- `eval_online.py` 鏄?*楠ㄦ灦**锛歚login()` / `chat()` / `tool_calls_of()` 闇€鎸変綘鐨勯」鐩绾︽敼鍐欙紱鏁版嵁闆嗘牱渚嬫潵鑷憚褰辫鍗曢」鐩紝鎹㈤」鐩繀椤绘暣浣撴浛鎹€?- 鍒ゅ畾閫昏緫鐨勫洖褰掕嚜妫€ monkeypatch 妯″潡绾у嚱鏁帮紝楠岃瘉鐨勬槸鍒ゅ畾绾緥锛屼笉鏄湡瀹炵綉缁滆矾寰勩€?- `EvalResults.java` 涓?`install.ps1` 鏈湪 CI 涓嚜鍔ㄩ獙璇侊紱鎺ュ叆鏃惰鍏堣窇涓€娆″啋鐑熴€?
## License

[MIT](LICENSE)
