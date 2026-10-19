-- ============================================================
-- lab_agent 演示数据：8 个实验室 + 32 台设备
-- 库：lab_agent    表：labs / equipments
-- 整个文件可以重复执行，不会再出现 1062 / 1452 报错。
--
-- 背景（2026-10-01 库里的实际状态）：
--   labs 已有 1、3、4~8 号，缺 2 号；equipments 为空。
--   equipments.lab_id 上有外键 equipments_ibfk_1 -> labs(id)，
--   而设备数据里用到了 lab_id=2，所以必须先补出 2 号实验室，
--   否则整段设备插入会因外键报 1452（多行 INSERT 是原子的，一行失败全丢）。
-- ============================================================

-- ------------------------------------------------------------
-- 0) 补上缺失的 2 号实验室（示波器、信号发生器等电子类设备挂在它下面）
--    用 ON DUPLICATE KEY UPDATE 写成幂等的，重跑不会报错
-- ------------------------------------------------------------
INSERT INTO labs (id, name, description, img, location, capacity, open_time, close_time, status, create_time, update_time)
VALUES (2, '电子实验室', '电子实验室', NULL, '综合实验楼201', 24, '08:00', '18:00', 1, NOW(), NOW())
ON DUPLICATE KEY UPDATE
  name        = VALUES(name),
  description = VALUES(description),
  location    = VALUES(location),
  capacity    = VALUES(capacity),
  open_time   = VALUES(open_time),
  close_time  = VALUES(close_time),
  status      = VALUES(status);

-- ------------------------------------------------------------
-- 1) 3 号实验室当前叫「人工智能实验室」，和 6 号重名，
--    但它的设备是光学/力学器材（光学实验台、氦氖激光器、力学轨道、分光计）
--    → 统一改成「物理实验室」。不想改就注释掉这一句。
-- ------------------------------------------------------------
UPDATE labs
SET name = '物理实验室', description = '物理实验室', location = '综合实验楼202'
WHERE id = 3;

-- ------------------------------------------------------------
-- 2) 1 号实验室的 location / open_time / close_time 原来是 NULL，
--    列表页会显示空白，顺手补全（不需要可注释掉）
-- ------------------------------------------------------------
UPDATE labs
SET location = '综合实验楼101', open_time = '08:00', close_time = '20:00'
WHERE id = 1;

-- ------------------------------------------------------------
-- 3) 4~8 号实验室：库里已经有了，这里改成幂等写法，
--    重跑只会把值刷新成下面的内容，不会再报 Duplicate entry '4'
-- ------------------------------------------------------------
INSERT INTO labs (id, name, description, img, location, capacity, open_time, close_time, status, create_time, update_time) VALUES
(4, '化学实验室',     '化学实验室',     NULL, '综合实验楼301', 20, '08:00', '18:00', 1, NOW(), NOW()),
(5, '生物实验室',     '生物实验室',     NULL, '综合实验楼302', 20, '08:00', '18:00', 1, NOW(), NOW()),
(6, '人工智能实验室', '人工智能实验室', NULL, '综合实验楼401', 30, '08:00', '18:00', 1, NOW(), NOW()),
(7, '机器人实验室',   '机器人实验室',   NULL, '综合实验楼402', 20, '09:00', '17:00', 1, NOW(), NOW()),
(8, '软件工程实验室', '软件工程实验室', NULL, '综合实验楼501', 40, '08:00', '20:00', 1, NOW(), NOW())
ON DUPLICATE KEY UPDATE
  name        = VALUES(name),
  description = VALUES(description),
  img         = VALUES(img),
  location    = VALUES(location),
  capacity    = VALUES(capacity),
  open_time   = VALUES(open_time),
  close_time  = VALUES(close_time),
  status      = VALUES(status),
  update_time = NOW();

-- ------------------------------------------------------------
-- 4) 32 台设备（equipments 现在是空的；INSERT IGNORE 保证重复执行不报 1062）
--    注意：IGNORE 会把主键冲突和被跳过一并吞掉，想确认插入结果就
--    SELECT COUNT(*) FROM equipments; 应该有 32 行。
-- ------------------------------------------------------------
INSERT IGNORE INTO equipments (id, lab_id, name, description, img, spec, quantity, status, create_time, update_time) VALUES
(1,  1, 'RTX4090',        '深度学习训练显卡', NULL, '24G 显存',          2,  1, NOW(), NOW()),
(2,  1, '开发主机',        '学生上机编程',     NULL, 'i7 / 32G / 1T SSD', 20, 1, NOW(), NOW()),
(3,  1, '投影仪',          '讲课演示',         NULL, '1080P',             1,  1, NOW(), NOW()),
(4,  1, '千兆交换机',      '机房组网',         NULL, '24 口',             1,  1, NOW(), NOW()),

(5,  2, '示波器',          '电路波形观测',     NULL, '100MHz 双通道',     8,  1, NOW(), NOW()),
(6,  2, '信号发生器',      '信号源实验',       NULL, 'DDS 60MHz',         6,  1, NOW(), NOW()),
(7,  2, '数字万用表',      '电子测量',         NULL, '4 位半',            10, 0, NOW(), NOW()),
(8,  2, '直流稳压电源',    '电路供电',         NULL, '30V 5A',            8,  1, NOW(), NOW()),

(9,  3, '光学实验台',      '几何光学实验',     NULL, '1.2m 隔振台',       4,  1, NOW(), NOW()),
(10, 3, '氦氖激光器',      '干涉衍射实验',     NULL, '632.8nm',           2,  1, NOW(), NOW()),
(11, 3, '力学轨道',        '牛顿定律实验',     NULL, '气垫导轨 1.5m',     3,  1, NOW(), NOW()),
(12, 3, '分光计',          '光谱测量',         NULL, '0.1° 精度',         4,  1, NOW(), NOW()),

(13, 4, '电子天平',        '试剂称量',         NULL, '0.1mg',             6,  1, NOW(), NOW()),
(14, 4, '离心机',          '样品分离',         NULL, '4000rpm',           2,  1, NOW(), NOW()),
(15, 4, '通风橱',          '有机实验',         NULL, '1.5m',              3,  1, NOW(), NOW()),
(16, 4, 'pH 计',           '溶液酸碱度',       NULL, '0.01pH',            4,  1, NOW(), NOW()),

(17, 5, '显微镜',          '细胞观察',         NULL, '1000x 光学',        10, 1, NOW(), NOW()),
(18, 5, '恒温培养箱',      '菌种培养',         NULL, '室温 ~ 60℃',        2,  1, NOW(), NOW()),
(19, 5, '移液器',          '微量取样',         NULL, '0.5-10μL',          20, 1, NOW(), NOW()),
(20, 5, 'PCR 仪',          '基因扩增',         NULL, '96 孔',             1,  0, NOW(), NOW()),

(21, 6, 'GPU 训练服务器',  '大模型微调',       NULL, '2 * RTX4090 / 128G', 1, 1, NOW(), NOW()),
(22, 6, 'RTX4090',        '深度学习训练显卡', NULL, '24G 显存',          4,  1, NOW(), NOW()),
(23, 6, '深度相机',        '视觉数据采集',     NULL, 'RealSense D435i',   3,  1, NOW(), NOW()),
(24, 6, '标注工作站',      '数据集标注',       NULL, 'i9 / 64G',          6,  1, NOW(), NOW()),

(25, 7, 'UR5 机械臂',      '工业机械臂教学',   NULL, '负载 5kg',          2,  1, NOW(), NOW()),
(26, 7, 'Livox 激光雷达',  'SLAM 建图',        NULL, 'Mid-360',           3,  1, NOW(), NOW()),
(27, 7, 'RealSense 深度相机', '视觉抓取',      NULL, 'D435i',             4,  1, NOW(), NOW()),
(28, 7, 'Jetson Orin',     '边缘计算',         NULL, '32G',               4,  1, NOW(), NOW()),

(29, 8, '开发主机',        '项目实训',         NULL, 'i7 / 32G / 1T SSD', 40, 1, NOW(), NOW()),
(30, 8, '显示器',          '双屏开发',         NULL, '27 寸 2K',          40, 1, NOW(), NOW()),
(31, 8, '投影仪',          '答辩演示',         NULL, '1080P',             2,  1, NOW(), NOW()),
(32, 8, '代码服务器',      'Git 与 CI',        NULL, '8 核 / 32G',        1,  1, NOW(), NOW());

-- ------------------------------------------------------------
-- 自检
-- ------------------------------------------------------------
SELECT l.id, l.name, l.location, COUNT(e.id) AS equipment_count
FROM labs l
LEFT JOIN equipments e ON e.lab_id = l.id
GROUP BY l.id, l.name, l.location
ORDER BY l.id;
