-- ============================================================
-- 预约并发安全：给 reservations 表补索引
--
-- 为什么需要单独跑这个脚本：
--   init_db() 里的 Base.metadata.create_all() 只会给「还不存在的表」建表建索引，
--   已经存在的 reservations 表不会被改动。所以老库升级要手动执行一次。
--
-- 为什么索引和并发安全有关：
--   create_reservation() 用 SELECT ... FOR UPDATE 加悲观锁，而 InnoDB 的行锁
--   是加在索引记录上的。如果冲突检测的查询条件没有合适索引，只能全表扫描，
--   行锁会退化成锁全表 —— 并发能力直接归零。
--
-- 脚本可重复执行（幂等），索引已存在时自动跳过。
-- ============================================================

DROP PROCEDURE IF EXISTS add_index_if_missing;

DELIMITER $$

CREATE PROCEDURE add_index_if_missing(
    IN p_table   VARCHAR(64),
    IN p_index   VARCHAR(64),
    IN p_columns VARCHAR(255)
)
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.statistics
        WHERE table_schema = DATABASE()
          AND table_name   = p_table
          AND index_name   = p_index
    ) THEN
        SET @ddl = CONCAT(
            'ALTER TABLE `', p_table, '` ADD INDEX `', p_index, '` (', p_columns, ')'
        );
        PREPARE stmt FROM @ddl;
        EXECUTE stmt;
        DEALLOCATE PREPARE stmt;
    END IF;
END$$

DELIMITER ;

-- 冲突检测的查询形状：lab_id + date + equipment_id 等值，start_time 范围
CALL add_index_if_missing(
    'reservations',
    'idx_lab_date_equip_start',
    '`lab_id`, `date`, `equipment_id`, `start_time`'
);

-- 60 秒兜底扫描按 status 过滤
CALL add_index_if_missing(
    'reservations',
    'idx_status',
    '`status`'
);

DROP PROCEDURE add_index_if_missing;

-- 验证：两条索引都应该出现在结果里
-- SHOW INDEX FROM reservations WHERE Key_name IN ('idx_lab_date_equip_start', 'idx_status');

-- 顺带确认隔离级别必须是 REPEATABLE-READ，否则间隙锁不生效，锁白加：
-- SELECT @@transaction_isolation;
