import discord
import aredis
import logging
from typing import Union, Set

import commands
import statics
import bgtasks
import apis
import config
from redisclient import redis


class SpaceXLaunchBotClient(discord.Client):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        logging.info("Client initialised")

        # Create asyncio tasks now
        self.loop.create_task(bgtasks.notification_task(self))

    async def on_ready(self):
        logging.info("Successfully connected to Discord API")
        await self.set_playing(config.BOT_GAME)
        await apis.dbl.update_guild_count(len(self.guilds))

    async def on_guild_join(self, guild):
        logging.info(f"Joined guild, ID: {guild.id}")
        await apis.dbl.update_guild_count(len(self.guilds))

    async def on_guild_remove(self, guild):
        logging.info(f"Removed from guild, ID: {guild.id}")
        await apis.dbl.update_guild_count(len(self.guilds))

        deleted = await redis.delete_guild_mentions(guild.id)
        if deleted != 0:
            logging.info(f"Removed guild settings for {guild.id}")

    async def on_message(self, message):
        if (
            not message.content.startswith(config.BOT_COMMAND_PREFIX)
            or message.author.bot
            or not message.guild
        ):
            # Not possibly a command (doesn't start with prefix)
            # Don't reply to bots (includes self)
            # Only reply to messages from guilds
            return

        # Commands can be in any case
        message_lower = message.content.lower()
        # Grab first word in the message (the command)
        first_word = message_lower.split(" ")[0]
        # Remove the command prefix so we can lookup the command
        command_used = first_word.replace(config.BOT_COMMAND_PREFIX, "")

        try:
            run_command = commands.CMD_FUNC_LOOKUP[command_used]
            # All commands are passed the client and the message objects
            to_send = await run_command(client=self, message=message)

        except KeyError:
            to_send = None

        except aredis.RedisError as ex:
            logging.error(f"RedisError occurred: {type(ex).__name__}: {ex}")
            to_send = statics.DB_ERROR_EMBED

        if to_send is None:
            return

        await self.send_s(message.channel, to_send)

    async def set_playing(self, title: str):
        await self.change_presence(activity=discord.Game(name=title))

    @staticmethod
    async def send_s(
        channel: discord.TextChannel, to_send: Union[str, discord.Embed]
    ) -> int:
        """Sends a text / embed message to a channel safely
        If an error occurs, safely suppress it so the bot doesn't crash
        Returns:
          0 : Success
         -1 : Message / embed / embed.title too long
         -2 : Nothing to send (to_send is not a string or Embed)
         -3 : Forbidden (No permission to message this channel)
         -4 : HTTPException (API down, network issues, etc.)
        """
        try:
            if isinstance(to_send, str):
                if len(to_send) > 2000:
                    return -1
                await channel.send(to_send)
                return 0
            if isinstance(to_send, discord.Embed):
                if len(to_send) > 2048 or len(to_send.title) > 256:
                    return -1
                await channel.send(embed=to_send)
                return 0
            return -2
        except discord.errors.Forbidden:
            return -3
        except discord.errors.HTTPException:
            return -4

    async def send_all_subscribed(
        self, to_send: Union[str, discord.Embed], send_mentions: bool = False
    ) -> Set[int]:
        """Send all subscribed channels to_send
        If send_mentions is true, get mentions from redis and send as well
        Returns a set of channels that are invalid -> should be unsubscribed
        """
        channel_ids = await redis.get_subbed_channels()
        invalid_ids = set()

        for channel_id in channel_ids:
            channel = self.get_channel(channel_id)

            if channel is None:
                invalid_ids.add(channel_id)

            else:
                await self.send_s(channel, to_send)

                if send_mentions:
                    mentions = await redis.get_guild_mentions(channel.guild.id)
                    if mentions != "":
                        await self.send_s(channel, mentions)

        return invalid_ids