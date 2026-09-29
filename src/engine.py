"""帮派技能 - 带6个bug"""
from dataclasses import dataclass, field

@dataclass
class GuildSkill:
    sid: str
    name: str
    max_level: int
    cost_per_level: dict

class GuildSkillSystem:
    def __init__(self):
        self.skills: dict[str, GuildSkill] = {}
        self.guild_research = {}  # bug3: 全局共享
        self.member_contrib = {}
        self.research_queue = []  # bug6: 无限制

    def start_research(self, guild_id, skill_id):
        # bug1: 只消耗资金不消耗时间
        if guild_id not in self.guild_research:
            self.guild_research[guild_id] = {}
        self.guild_research[guild_id][skill_id] = 1
        self.research_queue.append((guild_id, skill_id))
        return True

    def learn_skill(self, player_id, guild_id, skill_id):
        # bug2: 不看个人贡献
        level = self.guild_research.get(guild_id, {}).get(skill_id, 0)
        return level > 0

    def get_skill_effects(self, player_id, guild_id):
        # bug5: 加法叠加
        total = {}
        for sid, level in self.guild_research.get(guild_id, {}).items():
            total[sid] = level * 5
        return total

    def disband_guild(self, guild_id):
        # bug4: 直接删除
        if guild_id in self.guild_research:
            del self.guild_research[guild_id]
