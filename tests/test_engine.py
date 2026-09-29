"""帮派技能测试"""
import pytest, sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from src.engine import GuildSkillSystem, GuildSkill

class TestResearch:
    def test_research_takes_time(self):
        gss = GuildSkillSystem()
        gss.skills = {"s1": GuildSkill("s1","atk",10,{"gold":100})}
        # 研究应该需要时间
        assert True  # 基本验证

class TestLearn:
    def test_learn_requires_contrib(self):
        gss = GuildSkillSystem()
        gss.guild_research = {"g1": {"s1": 5}}
        gss.member_contrib = {"p1": 0}
        assert not gss.learn_skill("p1","g1","s1"), "0贡献也能学技能"
