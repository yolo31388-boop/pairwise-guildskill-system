"""帮派技能系统 - 修复版

修复的 6 个 bug:
1. 研究只消耗资金不消耗时间 -> 研究需要资金 + 时间，有进度条
2. 学习技能不看个人贡献 -> 学习消耗个人贡献，不足不能学
3. 研究进度全局共享 -> 每个帮派独立的研究状态
4. 解散直接删除技能数据 -> 成员技能按比例冻结保留，换帮有过渡期
5. 技能效果加法叠加 -> 乘区叠加，与其他系统加成不冲突
6. 研究队列无限制 -> 同时只能研究 1 个，队列有上限
"""
from dataclasses import dataclass, field


@dataclass
class GuildSkill:
    sid: str
    name: str
    max_level: int
    cost_per_level: dict  # {"gold": 资金, "contrib": 学习贡献, "time": 研究秒数}


@dataclass
class ResearchTask:
    guild_id: str
    skill_id: str
    started_at: float
    duration: float

    def progress(self, now: float) -> float:
        if self.duration <= 0:
            return 1.0
        return min(1.0, max(0.0, (now - self.started_at) / self.duration))

    def is_done(self, now: float) -> bool:
        return self.progress(now) >= 1.0


class GuildSkillSystem:
    # 同时只能研究 1 个，排队上限（含进行中的）
    MAX_CONCURRENT_RESEARCH = 1
    MAX_QUEUE_SIZE = 3
    # 解散后技能保留比例
    DISBAND_RETENTION = 0.5
    # 换帮过渡期（秒），过渡期内冻结技能只有一半效果
    TRANSITION_PERIOD = 7 * 24 * 3600
    # 每级技能效果（乘区）
    EFFECT_PER_LEVEL = 0.05

    def __init__(self):
        self.skills: dict[str, GuildSkill] = {}
        # bug3 修复: 每个帮派独立的研究等级 {guild_id: {skill_id: level}}
        self.guild_research: dict[str, dict[str, int]] = {}
        self.guild_funds: dict[str, int] = {}
        self.member_contrib: dict[str, int] = {}
        # 成员已学技能 {player_id: {skill_id: level}}
        self.member_skills: dict[str, dict[str, int]] = {}
        # 解散冻结的技能 {player_id: {skill_id: level}}
        self.frozen_skills: dict[str, dict[str, int]] = {}
        # 换帮时间 {player_id: 加入时间}，用于过渡期
        self.member_joined_at: dict[str, float] = {}
        # bug6 修复: 研究队列，同时只有 1 个进行中，其余排队
        self.research_queue: list[ResearchTask] = []
        self._now = 0.0

    # ---------- 时间 ----------

    def advance_time(self, seconds: float) -> None:
        """推进系统时间，完成到期的研究。"""
        self._now += seconds
        self._complete_finished()

    def _complete_finished(self) -> None:
        while self.research_queue and self.research_queue[0].is_done(self._now):
            task = self.research_queue.pop(0)
            levels = self.guild_research.setdefault(task.guild_id, {})
            skill = self.skills.get(task.skill_id)
            cap = skill.max_level if skill else 1
            levels[task.skill_id] = min(cap, levels.get(task.skill_id, 0) + 1)
            # 队首完成后，下一个排队任务开始计时
            if self.research_queue:
                nxt = self.research_queue[0]
                nxt.started_at = max(nxt.started_at, task.started_at + task.duration)

    # ---------- 研究 ----------

    def _guild_tasks(self, guild_id: str) -> list[ResearchTask]:
        return [t for t in self.research_queue if t.guild_id == guild_id]

    def start_research(self, guild_id: str, skill_id: str) -> bool:
        """开始研究：消耗帮派资金，占用队列，需要时间完成。"""
        skill = self.skills.get(skill_id)
        if skill is None:
            return False
        current = self.guild_research.get(guild_id, {}).get(skill_id, 0)
        queued = len(self._guild_tasks(guild_id))
        if current + queued >= skill.max_level:
            return False
        # bug6 修复: 队列上限
        if queued >= self.MAX_QUEUE_SIZE:
            return False
        # bug1 修复: 消耗资金
        cost = skill.cost_per_level.get("gold", 0)
        if self.guild_funds.get(guild_id, 0) < cost:
            return False
        self.guild_funds[guild_id] = self.guild_funds.get(guild_id, 0) - cost
        # bug1 修复: 研究需要时间；非队首任务等前面完成后才开始计时
        duration = skill.cost_per_level.get("time", 0)
        started_at = self._now
        if self.research_queue:
            last = self.research_queue[-1]
            started_at = max(self._now, last.started_at + last.duration)
        self.research_queue.append(ResearchTask(guild_id, skill_id, started_at, duration))
        return True

    def research_progress(self, guild_id: str, skill_id: str) -> float:
        """研究进度条 0.0 ~ 1.0；已完成的研究返回 1.0。"""
        for task in self._guild_tasks(guild_id):
            if task.skill_id == skill_id:
                return task.progress(self._now)
        if self.guild_research.get(guild_id, {}).get(skill_id, 0) > 0:
            return 1.0
        return 0.0

    # ---------- 学习 ----------

    def learn_skill(self, player_id: str, guild_id: str, skill_id: str) -> bool:
        """学习技能：消耗个人贡献，贡献不足不能学。"""
        guild_level = self.guild_research.get(guild_id, {}).get(skill_id, 0)
        learned = self.member_skills.get(player_id, {}).get(skill_id, 0)
        if guild_level <= 0 or learned >= guild_level:
            return False
        # bug2 修复: 检查并消耗个人贡献
        skill = self.skills.get(skill_id)
        cost = skill.cost_per_level.get("contrib", 1) if skill else 1
        if self.member_contrib.get(player_id, 0) < cost:
            return False
        self.member_contrib[player_id] -= cost
        self.member_skills.setdefault(player_id, {})[skill_id] = learned + 1
        return True

    # ---------- 效果 ----------

    def _effective_level(self, player_id: str, guild_id: str, skill_id: str) -> float:
        learned = self.member_skills.get(player_id, {}).get(skill_id, 0)
        guild_level = self.guild_research.get(guild_id, {}).get(skill_id, 0)
        level = min(learned, guild_level) if guild_level > 0 else 0
        # bug4 修复: 换帮过渡期内，冻结技能按一半生效
        frozen = self.frozen_skills.get(player_id, {}).get(skill_id, 0)
        joined = self.member_joined_at.get(player_id)
        if frozen > 0 and joined is not None:
            factor = 0.5 if self._now - joined < self.TRANSITION_PERIOD else 1.0
            level = max(level, min(frozen, guild_level) * factor)
        return level

    def get_skill_effects(self, player_id: str, guild_id: str) -> dict:
        """返回乘区效果：每个技能一个独立乘区，总加成为乘法叠加。

        例如 10 个技能各 5%: 1.05 ** 10 ≈ 1.629，而不是加法 1.5。
        与其他系统的加成处于不同乘区，互不冲突。
        """
        multipliers = {}
        sids = set(self.member_skills.get(player_id, {})) | set(
            self.frozen_skills.get(player_id, {})
        )
        for sid in sids:
            level = self._effective_level(player_id, guild_id, sid)
            if level > 0:
                multipliers[sid] = 1.0 + self.EFFECT_PER_LEVEL * level
        total = 1.0
        for m in multipliers.values():
            total *= m
        multipliers["total_multiplier"] = total
        return multipliers

    # ---------- 解散 / 换帮 ----------

    def disband_guild(self, guild_id: str) -> None:
        """解散帮派：成员已学技能按比例冻结保留，而不是直接删除。"""
        # 取消该帮派未开始的研究（进行中的不退资金，简化处理）
        self.research_queue = [t for t in self.research_queue if t.guild_id != guild_id]
        levels = self.guild_research.pop(guild_id, {})
        if not levels:
            return
        for player_id, learned in self.member_skills.items():
            frozen = self.frozen_skills.setdefault(player_id, {})
            for sid, lv in learned.items():
                if sid in levels and lv > 0:
                    kept = max(1, int(lv * self.DISBAND_RETENTION))
                    frozen[sid] = max(frozen.get(sid, 0), kept)
            # 已冻结的技能从在帮技能中移除，换帮后走冻结/过渡期逻辑
            for sid in levels:
                learned.pop(sid, None)

    def join_guild(self, player_id: str, guild_id: str) -> None:
        """加入新帮派：记录时间，冻结技能进入过渡期。"""
        self.member_joined_at[player_id] = self._now
