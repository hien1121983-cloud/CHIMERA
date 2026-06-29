"""CLI runner cho WorldGenesis.

Usage:
  python world_genesis_runner.py           # Chỉ chạy nếu chưa genesis
  python world_genesis_runner.py --force   # Chạy lại bất kể đã genesis chưa
"""
import argparse
import logging
import sys
import os
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s - [%(levelname)s] - %(name)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("world_genesis.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("WorldGenesisRunner")


def main():
    parser = argparse.ArgumentParser(
        description="CHIMERA WorldGenesis — Sinh nền móng thế giới bằng 1 LLM call."
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Chạy lại WorldGenesis dù đã hoàn tất trước đó.",
    )
    args = parser.parse_args()

    # Kiểm tra env vars tối thiểu
    required_envs = ["MONGODB_URI_PERMANENT"]
    missing = [e for e in required_envs if not os.getenv(e)]
    if missing:
        logger.critical(f"Thiếu biến môi trường: {missing}")
        sys.exit(1)

    logger.info("=" * 60)
    logger.info("CHIMERA WorldGenesis Runner v1.0")
    logger.info("=" * 60)

    # Import sau khi env đã load
    from core.db_client import ChimeraDB
    from simulator.world_genesis import WorldGenesis

    db = ChimeraDB()
    genesis = WorldGenesis(db=db)

    if genesis.is_completed() and not args.force:
        logger.info("✅ WorldGenesis đã hoàn tất trước đó. Không cần chạy lại.")
        logger.info("   Dùng --force để override.")

        # In trạng thái hiện tại
        _print_current_status(db)
        sys.exit(0)

    if args.force:
        logger.warning("⚠️  --force mode: Sẽ xóa và tạo lại toàn bộ world foundation.")

    logger.info("🌍 Bắt đầu WorldGenesis...")
    success = genesis.run(force=args.force)

    if success:
        logger.info("✅ WorldGenesis hoàn tất thành công!")
        _print_current_status(db)
        sys.exit(0)
    else:
        logger.error("❌ WorldGenesis thất bại. Xem log ở trên để biết chi tiết.")
        sys.exit(1)


def _print_current_status(db):
    """In tóm tắt trạng thái world sau genesis."""
    try:
        from simulator.engines.world_map_engine import WorldMapEngine
        from simulator.engines.world_history_engine import WorldHistoryEngine
        from simulator.engines.world_rules_engine import WorldRulesEngine

        map_eng     = WorldMapEngine(db)
        history_eng = WorldHistoryEngine(db)
        rules_eng   = WorldRulesEngine(db)

        zones   = map_eng.get_all_zones()
        history = history_eng.get_era_summary()
        rules   = rules_eng.get_active_rules()

        logger.info("-" * 40)
        logger.info(f"🗺️  WorldMap   : {len(zones)} zones")
        logger.info(f"📜 WorldHistory: {history}")
        logger.info(f"📋 WorldRules  : {len(rules)} rules active")
        logger.info("-" * 40)

        contested = map_eng.get_contested_zones()
        if contested:
            logger.info(f"⚔️  Contested zones: {[z['name'] for z in contested]}")

    except Exception as e:
        logger.warning(f"Không thể in status: {e}")


if __name__ == "__main__":
    main()
