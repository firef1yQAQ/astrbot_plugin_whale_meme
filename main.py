"""Meme dressing for AstrBot.

1. Replaces ``&&category&&`` markers produced by the model with real images
   from the meme packs installed by ``meme_manager``.
2. When no marker is present, picks an image by keyword matching on the
   incoming message + the reply, with a configurable probability.
3. Hard-limits the fish emoji so it never spams every sentence.

The default pack root is the standard ``meme_manager`` data directory, so the
plugin works on any installation without extra configuration.
"""

import random
import re
from pathlib import Path

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.message_components import Image, Plain
from astrbot.api.star import Context, Star, register

try:
    from astrbot.core.utils.astrbot_path import get_astrbot_plugin_data_path

    PACKS_ROOT = Path(get_astrbot_plugin_data_path()) / "meme_manager" / "packs"
except Exception:  # pragma: no cover - very old AstrBot builds
    PACKS_ROOT = Path("data/plugin_data/meme_manager/packs")

MARKER_RE = re.compile(r"&&\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*&&")
IMAGE_EXT = {".gif", ".png", ".jpg", ".jpeg", ".webp"}

KEYWORD_RULES = [
    ("food", ["白饭", "吃饭", "吃啥", "好吃", "饭", "零食", "饿", "馋", "奶茶", "外卖"]),
    ("sleep", ["睡", "困", "晚安", "熬夜", "躺"]),
    ("angry", ["滚", "闭嘴", "你再说", "气死", "烦", "别吵"]),
    ("sad", ["呜呜", "难受", "哭", "委屈", "惨", "破防", "寄了"]),
    ("happy", ["哈哈", "笑死", "好耶", "开心", "爽", "牛", "厉害", "赞", "绷不住"]),
    ("confused", ["?", "？", "啥", "不懂", "啊这", "什么鬼"]),
    ("surprised", ["我超", "卧槽", "真的假的", "居然", "离谱"]),
    ("shy", ["嘿嘿", "害羞", "别夸", "不好意思"]),
    ("money", ["钱", "红包", "工资", "氪", "充"]),
    ("work", ["上班", "加班", "摸鱼", "电脑"]),
    ("entertainment", ["游戏", "唱歌", "跳舞", "视频", "电影"]),
    ("affection", ["喜欢", "抱", "贴贴", "亲", "摸摸"]),
    ("greeting", ["在吗", "来了", "早", "嗨"]),
    ("teasing", ["笑死", "典", "就这", "菜"]),
]


@register(
    "astrbot_plugin_whale_meme",
    "dsh",
    "把 &&分类&& 标记换成真实表情包，并按上下文概率自动配图",
    "0.3.0",
)
class WhaleMeme(Star):
    def __init__(self, context: Context, config: dict | None = None):
        super().__init__(context)
        self.conf = config or {}
        custom = str(self._opt("pack_dir", "") or "").strip()
        self.packs_root = Path(custom) if custom else PACKS_ROOT
        self._category_index: dict[str, list[str]] = {}
        self._index_built = False

    def _opt(self, key, default):
        try:
            value = self.conf.get(key, default)
        except Exception:
            return default
        return default if value is None else value

    def _build_index(self) -> None:
        index: dict[str, list[str]] = {}
        if self.packs_root.is_dir():
            for pack in self.packs_root.iterdir():
                memes = pack / "memes"
                if not memes.is_dir():
                    continue
                for category in memes.iterdir():
                    if not category.is_dir():
                        continue
                    files = [
                        str(p)
                        for p in category.iterdir()
                        if p.is_file() and p.suffix.lower() in IMAGE_EXT
                    ]
                    if files:
                        index.setdefault(category.name.lower(), []).extend(files)
        self._category_index = index
        self._index_built = True
        logger.info(
            "[whale_meme] index built: %d categories / %d images",
            len(index),
            sum(len(v) for v in index.values()),
        )

    def _pick(self, tag: str) -> str | None:
        if not self._index_built:
            self._build_index()
        files = self._category_index.get(tag.lower())
        if not files:
            files = self._category_index.get("teasing") or self._category_index.get("happy")
        return random.choice(files) if files else None

    def _guess_tag(self, text: str) -> str:
        for tag, words in KEYWORD_RULES:
            if any(word in text for word in words):
                return tag
        return "teasing"

    @filter.on_decorating_result(priority=200000)
    async def swap_markers(self, event: AstrMessageEvent):
        if not bool(self._opt("enable", True)):
            return
        result = event.get_result()
        chain = getattr(result, "chain", None)
        if not result or not chain:
            return

        tags: list[str] = []
        new_chain: list = []
        plain_text = ""
        has_media = False
        for comp in chain:
            if isinstance(comp, Plain):
                text = comp.text or ""
                plain_text += text
                found = MARKER_RE.findall(text)
                if found:
                    tags.extend(found)
                    text = MARKER_RE.sub("", text)
                    text = re.sub(r"\n{2,}", "\n", text).strip()
                if text:
                    new_chain.append(Plain(text))
            else:
                if str(getattr(comp, "type", "")) in {"image", "record", "video", "file"}:
                    has_media = True
                new_chain.append(comp)

        if not new_chain:
            return

        # 98% of the time the fish emoji is removed entirely.
        keep_fish = random.random() < float(self._opt("fish_emoji_probability", 0.02))
        cleaned: list = []
        for comp in new_chain:
            if isinstance(comp, Plain):
                t = comp.text or ""
                kept = False
                if keep_fish and "🐟" in t:
                    t = t.replace("🐟", "", 1)
                    kept = True
                t = t.replace("🐟", "").replace(">_<", "")
                if kept:
                    t = t.rstrip() + " 🐟"
                t = re.sub(r"[ \t]{2,}", " ", t).strip()
                if t:
                    cleaned.append(Plain(t))
            else:
                cleaned.append(comp)
        if cleaned:
            new_chain = cleaned

        images = []
        if tags:
            seen = []
            for tag in tags:
                if tag.lower() not in seen:
                    seen.append(tag.lower())
            for tag in seen[: int(self._opt("max_per_reply", 1))]:
                path = self._pick(tag)
                if path:
                    images.append(Image.fromFileSystem(path))
        elif not has_media and random.random() < float(self._opt("auto_probability", 0.2)):
            context_text = plain_text
            try:
                incoming = str(event.message_str or "")
                if incoming:
                    context_text = incoming + "\n" + plain_text
            except Exception:
                pass
            path = self._pick(self._guess_tag(context_text))
            if path:
                images.append(Image.fromFileSystem(path))

        result.chain = images if images else new_chain
