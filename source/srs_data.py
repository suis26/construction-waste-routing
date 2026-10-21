# -*- coding: utf-8 -*-
"""
SRS-Route 算例数据

对齐 PPT《建筑垃圾运输优化平台第一版》:
  第 3 页  五类建筑垃圾
  第 5 页  空驶绕行 / 等待积压 / 拒收返运 / 质量销路
  第 7 页  输入(产生点/处理点/车辆) 与输出(处理点+时段/车辆+顺次/接续)
  第 9 页  基准案例: A/B/C 各 4 吨, 12 吨车, D 兼作发车点
  第 12 页 综合成本 = 行驶成本 + 等待成本 + 处置费用 + 违约惩罚
  第 14 页 材质标签与潜在利用方向

成本参数由第 9 页两场景反解:
  分别直送 120 km / 900 元   多点集运 50 km / 350 元
  900 = 3F + 120m,  350 = F + 50m   =>  F = 100 元/趟,  m = 5 元/km
"""
import math

# ---- 成本参数(由 PPT 第 9 页反解, 见模块说明) ----
FIXED_TRIP_COST = 100.0    # 元/趟, 出车固定成本
COST_PER_KM     = 5.0      # 元/km
WAIT_COST_PER_H = 60.0     # 元/小时, 车辆等待成本
LATE_PENALTY_H  = 200.0    # 元/小时, 超交付期限违约惩罚
HANDLE_COST_T   = 2.0      # 元/吨, 额外装卸操作成本
CO2_PER_KM      = 0.9      # kgCO2e/km, 12 吨级货车近似

# ---- 车辆与作业参数 ----
TRUCK_T  = 12.0            # 吨
TRUCK_M3 = 16.0            # 方
RUN_KMH  = 70.0            # km/h, 由第9页两场景联立反解
LOAD_MIN_T = 15.7142857 / 4.0   # min/吨, 使4吨装货=15.714min
UNLOAD_MIN_T = 2.0         # min/吨, 卸货

# ---- PPT 第 3 页: 五类建筑垃圾 ----
CATEGORIES = ['工程渣土', '工程泥浆', '工程垃圾', '拆除垃圾', '装修垃圾']

# ---- PPT 第 14 页: 材质标签 -> 潜在利用方向 ----
MATERIAL_REUSE = {
    '混凝土砖瓦': '再生骨料、道路材料',
    '金属':       '分选后进入金属回收链',
    '木材':       '分类回收或专门处理',
    '塑料':       '分类回收或专门处理',
    '石膏':       '石膏再生利用',
    '土与泥浆':   '土方平衡或专项处理',
}

# 各处理设施接收的材质(用于接收匹配)
# 对照 PPT 第 14 页"材质标签 -> 潜在利用方向"与第 3 页五类口径
DEPOT_ACCEPT = {
    '资源化厂':   ['混凝土砖瓦', '石膏'],
    '消纳场':     ['混凝土砖瓦', '石膏'],
    '金属回收':   ['金属'],
    '分拣中转场': ['木材', '塑料'],
    '泥浆预处理': ['土与泥浆'],
    '土方平衡点': ['土与泥浆'],
}

# 同一材质可被多类设施接收时, 再按"订单类别"区分去向。
# 泥浆必须先预脱水(上海规定第六条 / 深圳办法第十八条);
# 渣土不得进中转场或资源化厂, 只能走土方平衡点。
CATEGORY_ALLOWED_KIND = {
    '工程渣土': {'土方平衡点'},
    '工程泥浆': {'泥浆预处理'},
    '工程垃圾': {'资源化厂', '消纳场', '金属回收'},
    '拆除垃圾': {'资源化厂', '消纳场', '金属回收'},
    '装修垃圾': {'资源化厂', '消纳场', '分拣中转场'},
}

PREPROCESS_REQUIRED = {'工程泥浆'}


def dist(a, b):
    return math.hypot(a['x'] - b['x'], a['y'] - b['y'])


def ppt_case():
    """
    PPT 第 9 页原案例, 几何经过构造使两组里程精确复现:
      D 为原点, A/B/C 均在距 D 20 km 的圆弧上, 张角 2*asin(0.125)
      分别直送 = 3 x (20+20) = 120 km
      多点集运 = 20 + 5 + 5 + 20 = 50 km
    """
    R = 20.0
    half = 2 * math.asin(0.125)      # 使 A->B = B->C = 5.0 km
    cx, sy = R * math.cos(half), R * math.sin(half)
    now = 8 * 60                     # 08:00 上班
    orders = [
        dict(id='A', cat='工程垃圾', mat='混凝土砖瓦', tons=4.0, vol=5.0,
             x=cx, y=-sy, ready=now, deadline=12 * 60,
             conf=0.92, risk='低', must_direct=False),
        dict(id='B', cat='工程垃圾', mat='混凝土砖瓦', tons=4.0, vol=5.0,
             x=R,  y=0.0, ready=now, deadline=12 * 60,
             conf=0.90, risk='低', must_direct=False),
        dict(id='C', cat='工程垃圾', mat='混凝土砖瓦', tons=4.0, vol=5.0,
             x=cx, y=sy,  ready=now, deadline=12 * 60,
             conf=0.88, risk='低', must_direct=False),
    ]
    depots = [dict(id='D', name='D资源化厂(兼发车点)', kind='资源化厂',
                   x=0.0, y=0.0, cap_t=1e9, open_t=now, close_t=20 * 60,
                   fee_per_t=0.0, accepts=DEPOT_ACCEPT['资源化厂'])]
    vehicles = [dict(id='V1', cap_t=TRUCK_T, cap_m3=TRUCK_M3, start='D',
                     avail=now, types=list(DEPOT_ACCEPT['资源化厂']))]
    return orders, depots, vehicles


def expanded_case():
    """
    五类建筑垃圾扩展场景: 14 个产生点, 4 个处理设施, 4 台车。
    含材质标签与视觉置信度, 用于接收匹配与拒收风险预筛。
    """
    now = 8 * 60
    O = [
        # 工程渣土(仅土方平衡/消纳)
        dict(id='T1', cat='工程渣土', mat='土与泥浆', tons=6.0, vol=5.0, x=6.0,  y=3.0,
             ready=now,      deadline=17 * 60, conf=0.95, risk='低', must_direct=False),
        dict(id='T2', cat='工程渣土', mat='土与泥浆', tons=5.0, vol=4.5, x=7.5,  y=4.5,
             ready=now,      deadline=17 * 60, conf=0.93, risk='低', must_direct=False),
        dict(id='T3', cat='工程渣土', mat='土与泥浆', tons=4.5, vol=4.0, x=5.0,  y=6.0,
             ready=now + 90, deadline=17 * 60, conf=0.91, risk='低', must_direct=False),
        # 工程泥浆(必须先预处理)
        dict(id='M1', cat='工程泥浆', mat='土与泥浆', tons=6.0, vol=6.0, x=14.0, y=12.0,
             ready=now,      deadline=17 * 60, conf=0.90, risk='低', must_direct=True),
        dict(id='M2', cat='工程泥浆', mat='土与泥浆', tons=5.0, vol=5.0, x=15.5, y=13.0,
             ready=now + 60, deadline=17 * 60, conf=0.88, risk='低', must_direct=True),
        # 工程垃圾
        dict(id='E1', cat='工程垃圾', mat='混凝土砖瓦', tons=6.0, vol=6.0, x=22.0, y=6.0,
             ready=now,      deadline=12 * 60, conf=0.94, risk='低', must_direct=False),
        dict(id='E2', cat='工程垃圾', mat='金属',       tons=3.0, vol=3.0, x=23.5, y=7.5,
             ready=now,      deadline=12 * 60, conf=0.86, risk='中', must_direct=False),
        dict(id='E3', cat='工程垃圾', mat='混凝土砖瓦', tons=5.5, vol=5.5, x=21.0, y=8.5,
             ready=now + 120, deadline=12 * 60, conf=0.92, risk='低', must_direct=False),
        # 拆除垃圾
        dict(id='D1', cat='拆除垃圾', mat='混凝土砖瓦', tons=6.0, vol=5.0, x=9.0, y=20.0,
             ready=now,      deadline=17 * 60, conf=0.89, risk='低', must_direct=False),
        dict(id='D2', cat='拆除垃圾', mat='金属',       tons=3.0, vol=2.5, x=10.5, y=21.5,
             ready=now + 45, deadline=17 * 60, conf=0.84, risk='中', must_direct=False),
        # 装修垃圾(成分杂, 需先分拣)
        dict(id='R1', cat='装修垃圾', mat='木材',   tons=4.5, vol=6.0, x=26.0, y=18.0,
             ready=now,      deadline=15 * 60, conf=0.72, risk='高', must_direct=False),
        dict(id='R2', cat='装修垃圾', mat='石膏',   tons=3.5, vol=5.0, x=27.5, y=19.5,
             ready=now + 30, deadline=15 * 60, conf=0.68, risk='高', must_direct=False),
        dict(id='R3', cat='装修垃圾', mat='塑料',   tons=3.0, vol=5.5, x=25.0, y=20.0,
             ready=now + 60, deadline=15 * 60, conf=0.66, risk='高', must_direct=False),
        dict(id='R4', cat='装修垃圾', mat='混凝土砖瓦', tons=5.0, vol=5.0, x=28.0, y=17.0,
             ready=now,      deadline=15 * 60, conf=0.80, risk='中', must_direct=False),
    ]
    D = [
        dict(id='Z1', name='Z1资源化厂', kind='资源化厂', x=24.0, y=10.0, cap_t=60.0,
             open_t=now, close_t=18 * 60, fee_per_t=22.0, accepts=DEPOT_ACCEPT['资源化厂']),
        dict(id='L1', name='L1消纳场', kind='消纳场', x=4.0, y=16.0, cap_t=45.0,
             open_t=now, close_t=18 * 60, fee_per_t=14.0, accepts=DEPOT_ACCEPT['消纳场']),
        dict(id='S1', name='S1金属回收', kind='金属回收', x=12.0, y=2.0, cap_t=20.0,
             open_t=now, close_t=17 * 60, fee_per_t=8.0, accepts=DEPOT_ACCEPT['金属回收']),
        dict(id='P1', name='P1分拣中转场', kind='分拣中转场', x=16.0, y=16.0, cap_t=40.0,
             open_t=now, close_t=18 * 60, fee_per_t=16.0, accepts=DEPOT_ACCEPT['分拣中转场']),
        dict(id='W1', name='W1泥浆预处理站', kind='泥浆预处理', x=17.0, y=10.0, cap_t=30.0,
             open_t=now, close_t=18 * 60, fee_per_t=35.0, accepts=DEPOT_ACCEPT['泥浆预处理']),
        dict(id='U1', name='U1土方平衡点', kind='土方平衡点', x=2.0, y=8.0, cap_t=60.0,
             open_t=now, close_t=18 * 60, fee_per_t=3.0, accepts=DEPOT_ACCEPT['土方平衡点']),
    ]
    V = [
        dict(id='V1', cap_t=12.0, cap_m3=16.0, start='Z1', avail=now,      types=['混凝土砖瓦', '石膏']),
        dict(id='V2', cap_t=12.0, cap_m3=16.0, start='L1', avail=now,      types=['混凝土砖瓦', '石膏']),
        dict(id='V3', cap_t=10.0, cap_m3=12.0, start='P1', avail=now + 30, types=['混凝土砖瓦', '金属', '木材', '塑料', '石膏', '土与泥浆']),
        dict(id='V4', cap_t=8.0,  cap_m3=10.0, start='S1', avail=now + 60, types=['金属']),
    ]
    return O, D, V
