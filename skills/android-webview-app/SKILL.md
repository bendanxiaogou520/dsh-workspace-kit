---
name: android-webview-app
description: "在本机给安卓打「WebView 壳 App」并装到真机：Gradle 构建、签名发版、file:// 路由坑、长按去浏览器感、自适应图标、本地资源打包、以及「电脑端数据热更新到手机」的模式。当要把一个 HTML 单页做成 APK、要改安卓壳的 Java、要装包到手机验证、或 APK 里出现「返回键退桌面 / 长按能选中文字 / 图标黑方块 / 图片 404 / 改了网页但装机没变」这类症状时使用。"
---

# 安卓 WebView 壳 App（本机实操）

适用：把一份 `index.html` 做成能长期用的 APK。
本机已落地三个：**玽游**（Steam 数据）、**玽词**（背单词）、**玽管家**（手机管家）。
它们结构几乎一样 —— 一套壳 + 一个越来越大的单页，**别另起炉灶**。

---

## 0. 工具链（已装好，直接用）

```
JDK    C:\android-toolchain\jdk\jdk-17.0.20.1+1
Gradle C:\android-toolchain\gradle\gradle-8.7        （玽游用的是 8.11.1 wrapper）
SDK    C:\android-toolchain\sdk                       （含 platform-tools\adb.exe）
```

**构建必须在 Windows 侧跑**，MSYS bash 里 `cmd //c build.bat` 开出来是**空壳**
（退出码 0 但什么都没做）：

```bash
# 正确
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "& cmd.exe /c '.\build.bat'"
```

产物：`android/app/build/outputs/apk/release/app-release.apk`

---

## 1. 工程骨架

```
android/
  app/build.gradle          ← versionCode / versionName / 签名 都在这
  app/src/main/AndroidManifest.xml
  app/src/main/java/<pkg>/MainActivity.java
  app/src/main/assets/index.html      ← 由 ../prototype/index.html 拷进来
  keys/<name>-release.jks
  keystore.properties
  build.bat
```

`build.gradle` 里两条 **Gradle 任务把网页和本地图拷进 assets**，挂在 `preBuild` 上：

```groovy
tasks.register('copyWebAsset', Copy) {
    from rootProject.file('../prototype/index.html')
    into layout.projectDirectory.dir('src/main/assets')
}
tasks.register('copyLocalImgs', Copy) {
    from rootProject.file('../prototype/img')
    into layout.projectDirectory.dir('src/main/assets/img')
    include '*.jpg', '*.jpeg', '*.png', '*.webp'
}
tasks.named('preBuild').configure { dependsOn 'copyWebAsset', 'copyLocalImgs' }
```

★ **少第二条就是「本地图片全部 404」** —— 只拷 index.html 的话 `assets/img/` 根本不存在。

---

## 2. MainActivity 骨架（含所有踩过的坑）

```java
WebSettings s = web.getSettings();
s.setJavaScriptEnabled(true);
s.setDomStorageEnabled(true);
s.setAllowFileAccess(true);
s.setCacheMode(WebSettings.LOAD_DEFAULT);

/* 关掉「浏览器感」—— 三层一起上，只做 CSS 在部分机型会被系统选区盖过 */
web.setLongClickable(false);
web.setOnLongClickListener(v -> true);
web.setOverScrollMode(WebView.OVER_SCROLL_NEVER);
web.addJavascriptInterface(new Bridge(), "Native");
web.loadUrl("file:///android_asset/index.html");
```

配套 JS（`killBrowserFeel()`）：拦 `contextmenu` / `selectstart` / `dragstart`，
并在 `touchend` / `selectionchange` 后清选区。CSS 侧 `user-select:none` + `-webkit-touch-callout:none`。

---

## 3. ★★★ 返回键：只能用 `location.hash`，不能用 `history.pushState`

**APK 里页面是 `file:///android_asset/index.html`。file:// 下 `pushState` / `replaceState` 会抛
`SecurityError`**，被 try/catch 吞掉后 → 历史栈从未增长 → `WebView.canGoBack()` 恒 false
→ 按返回键**直接退出 App**（表现就是"回桌面"）。

```js
/* 路由写 hash —— file:// 下赋值合法，且一定压入一条 WebView 历史 */
function setHash(h){ location.hash = h; }
window.addEventListener('hashchange', onHashChange);
```

Java 侧再补一层：JS 每次切屏调 `Native.setScreen(id)`，`onBackPressed` 据此决定
调 `goBack()` 还是真的退出。

```
★ 铁律：任何 history / storage / fetch 行为，浏览器 http:// 通过 ≠ APK file:// 通过。
   必须按协议差异复核。这条修了三次才找到。
```

---

## 4. 自适应图标：前景层必须透明底

`mipmap-anydpi-v26` 的 foreground **只能有图形本身，不能有底色**。
画成「黑底 + 圆角块 + 图形」叠在纯黑 `background` 上 = **一个黑方块，图形被吃掉**。

导出给桌面快捷方式用的 ico 时也可复用：`ic_launcher_foreground.png`（432×432）比
`ic_launcher.png`（192×192）清晰得多。

---

## 5. ★★★ 数据热更新：adb push 到 App 私有目录

要「电脑上算好数据、手机上读」时，**不要让手机联网**（校园网会挡 api 域名，
而且 file:// 页面发不了跨域请求）。走这条路：

```
电脑端脚本读数据 → 生成 JSON
   → adb push 到 /sdcard/Android/data/<pkg>/files/xxx.json
   → App 里 Java 读文件（getExternalFilesDir(null)）
   → evaluateJavascript / @JavascriptInterface 把 JSON 交给网页合并
```

Java 侧：

```java
@JavascriptInterface
public String readLocalPlaytime() {
    File f = new File(getExternalFilesDir(null), "playtime.json");
    return f.exists() ? readFile(f) : "";
}
```

JS 侧：读 → `JSON.parse` → 合并进内存模型 → 重算统计 → 重绘。
**整个链路不依赖网络**，校园网/断网都能用。

配套脚本要做的：
1. `mkdir -p /sdcard/Android/data/<pkg>/files`
2. `adb push`
3. ★ **`adb push` 把 "1 file pushed" 写到 stderr**，判断成功要合并 stdout + stderr
4. 用 `wc -c` 回读确认字节数

设备选择**不要写死 IP**（校园网 DHCP 会变）→ 动态读 `adb devices` 取第一台在线设备。

---

## 6. 发版三步

```bash
# 1) 改 app/build.gradle 的 versionCode(+1) / versionName
# 2) 编译
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "& cmd.exe /c '.\build.bat'"
# 3) 复制出来 + 发版
cp app/build/outputs/apk/release/app-release.apk ../gouyou.apk
gh release create vX.Y.Z gouyou.apk -R <owner>/<repo>
```

签名复用同一份 `keys/*.jks`（口令在 `keystore.properties`），**换 key 会导致覆盖安装失败**。

装机：`adb -s <serial> install -r xxx.apk`
**`install -r` 有时会清空外部私有目录** → 装完要重新 push 一次数据文件。

---

## 7. 真机验证的边界

- 抓屏：`adb exec-out screencap -p > x.png`，再 `read_image` 看。
  截图很大（1260×2800），`maxWidth` 调到 430 左右才看得清文字。
- 点按：**坐标要按截图换算**，且**一轮点错立刻停手**（别连点硬试）。
- WebView **默认没开无障碍**，`uiautomator dump` 只出空节点 →
  想稳定点按，要么给页面补 `aria-label` + `setAccessibilityDelegate`，要么请他手动点。
- **动他手机前先问一句**（「手机能借我用下吗」）。

---

## 8. 症状 → 根因速查

| 症状 | 根因 | 修法 |
| --- | --- | --- |
| 返回键直接退桌面 | file:// 下 pushState 抛异常被吞 | 改 `location.hash` |
| 长按能选中文字 / 弹保存菜单 | WebView 默认行为 | CSS + Java + JS 三层关 |
| 图标是个黑方块 | foreground 有底色 | 前景层改透明底 |
| 本地图片全 404 | 没把 `img/` 打进 assets | 加 `copyLocalImgs` 任务 |
| 改了网页但装机没变 | assets 没重新拷 | 确认 `copyWebAsset` 挂在 preBuild |
| 双击 build.bat 没反应 | MSYS 里 `cmd //c` 是空壳 | 走 `powershell -Command "& cmd.exe /c ..."` |
| APK 变成 6 字节文本 | bat 里 `copy` 后面跟了 `echo OK -> x.apk` | bat 只编译，复制在外面做 |
| 安装后数据文件没了 | `install -r` 清了外部目录 | 装完重新 push |
| 某个 render 的开关永久消失 | 上一个分支设死 `display:none` 没恢复 | **进函数先无条件重置** |

---

## 9. 交付给他时

- **APK 直接给下载链接**（他自己会装），或 `adb install` 帮装上。
- 说清版本号和这一版改了什么。
- 中间产物（截图、临时 apk、dump 出来的 xml）**当场删**。
