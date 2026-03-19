import logging
import textwrap
from typing import TYPE_CHECKING

from .cog import Boss

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot

log = logging.getLogger("ballsdex.packages.boss")

LOGO = textwrap.dedent(r"""
    +---------------------------------------+
    |      BallsDex Boss Pack v3.0         |
    |        Licensed under MIT             | 
    |            BETA [0.1]                 |
    +---------------------------------------+
""").strip()


async def setup(bot: "BallsDexBot"):
    print(LOGO)
    log.info("Loading Boss package...")
    await bot.add_cog(Boss(bot))
    log.info("Boss package loaded successfully!")
