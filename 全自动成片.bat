@echo off
chcp 65001 >nul
cd /d "%~dp0"
rem 改成你的 IndexTTS2 venv 里的 python（或任意含 indextts 的解释器）
set PY=%PY%

if "%~1"=="" (
  echo 三段式全自动：粗剪→细剪→文案→配音→合成。把录屏视频拖到本 bat 图标上
  pause
  exit /b 1
)

where ffmpeg >nul 2>nul || (echo [!] 找不到 ffmpeg，请重开终端再试 & pause & exit /b 1)
if not exist glm_key.txt (echo [!] 缺少 glm_key.txt（智谱 API Key）& pause & exit /b 1)

copy /y "%~1" game.mp4 >nul

echo [1/4] 粗剪：AI 全片扫描，剔除非游戏画面（约5分钟）...
%PY% 10_粗剪.py || (echo 粗剪失败 & pause & exit /b 1)

start notepad 粗剪时间线.txt
echo 【粗剪时间线已打开：▶=保留 ✂=剪掉。看完回本窗口按键进入细剪；想改叙事可手动编辑后跳过下一步】
pause >nul

echo [2/4] 细剪：AI 决定叙事结构 + 逐段写文案...
%PY% 20_细剪.py || (echo 细剪失败 & pause & exit /b 1)

start notepad 解说稿.txt
echo 【解说稿可改可不改，改完回本窗口按键继续配音】
pause >nul

echo [3/4] 分段克隆音色配音...
%PY% 01_配音.py || (echo 配音失败 & pause & exit /b 1)

echo [4/4] 配音驱动剪辑合成（声画逐段对齐+字幕+BGM+画中画）...
%PY% 03_剪辑.py || (echo 合成失败 & pause & exit /b 1)

echo [5] 封面 + 竖屏版 + 验收图 + 剪映草稿...
%PY% 30_封面.py
%PY% 31_竖屏.py
%PY% 32_验收.py
%PY% 33_剪映草稿.py

echo.
echo [完成] 产出：成片.mp4 / 竖屏版.mp4 / cover.jpg / 验收图.jpg / 投稿信息.txt / 剪映精修草稿
pause
