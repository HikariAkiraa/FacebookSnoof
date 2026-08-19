"""Main entrypoint and orchestrator for FacebookSnoof deal scraper and valuation engine."""

import os
import sys
import yaml
import random
import logging
import argparse
from datetime import datetime
from apscheduler.schedulers.blocking import BlockingScheduler

# Force UTF-8 encoding for stdout on Windows terminal to support emojis safely
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from database.db import DatabaseManager
from engine.collector import FacebookCollector
from engine.filters import is_candidate_listing
from engine.evaluator import DealEvaluator
from notifier.telegram import TelegramNotifier
from notifier.discord import DiscordNotifier, start_discord_command_listener

# Ensure logs directory exists before logging setup
os.makedirs("logs", exist_ok=True)

# Configure logger
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("logs/facebooksnoof.log", encoding="utf-8")
    ]
)
logger = logging.getLogger("FacebookSnoof.Main")


def load_config(config_path: str = "config/config.yaml") -> dict:
    """Load configuration options from YAML file."""
    if not os.path.exists(config_path):
        logger.error(f"Configuration file not found at: {config_path}")
        sys.exit(1)
        
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def print_cycle_summary_report(cycle_results: list, total_scraped: int, total_phase1_passed: int, total_interesting: int, total_skipped: int) -> None:
    """Print clean human-intuitive summary report at the end of the entire scraping cycle."""
    interesting_items = [r for r in cycle_results if r["is_interesting"]]
    skipped_items = [r for r in cycle_results if not r["is_interesting"]]

    print("\n" + "=" * 80)
    print("                    📊 REKAPITULASI HASIL EVALUASI FACEBOOKSNOOF")
    print("=" * 80)

    # Section 1: High Score Deals (Passed Phase 2)
    print(f"\n🔥 [DEAL MENARIK / LOLOS PHASE 2] ({len(interesting_items)})")
    print("-" * 80)
    if interesting_items:
        for idx, r in enumerate(interesting_items, 1):
            print(f"{idx}. [{r['hardware_name']}]")
            print(f"   🏷️  Harga: Rp {r['asking_price']:,} (Pasar: Rp {r['estimated_market_price']:,} | Skor: {r['deal_score']}/100 - {r['verdict']})")
            print(f"   💡 Alasan: {r['reasoning']}")
            print(f"   📍 Grup: {r['group_name']}")
            print(f"   🔗 Link: {r['post_url']}\n")
    else:
        print("   (Tidak ada deal menarik pada siklus ini)\n")

    # Section 2: Passed Phase 1 but Skipped / Low Score in Phase 2
    print(f"⚠️ [LOLOS PHASE 1 TAPI DI-SKIP DI PHASE 2] ({len(skipped_items)})")
    print("-" * 80)
    if skipped_items:
        for idx, r in enumerate(skipped_items, 1):
            if r["is_valid_pc_hardware"]:
                price_info = f"Rp {r['asking_price']:,} (Pasar: Rp {r['estimated_market_price']:,} | Skor: {r['deal_score']}/100 - {r['verdict']})"
            else:
                price_info = f"Rp {r['asking_price']:,} | Status: Non-PC Hardware Core"
            
            print(f"{idx}. [{r['hardware_name']}]")
            print(f"   🏷️  Harga & Status: {price_info}")
            print(f"   💡 Alasan Skip: {r['reasoning']}")
            print(f"   📍 Grup: {r['group_name']}")
            print(f"   🔗 Link: {r['post_url']}\n")
    else:
        print("   (Tidak ada postingan yang di-skip di Phase 2)\n")

    print("=" * 80)
    print(f"📈 RINGKASAN SIKLUS: Total Scraped: {total_scraped} | Lolos Phase 1: {total_phase1_passed} | Deal Menarik: {total_interesting} | Skipped Phase 2: {total_skipped}")
    print("=" * 80 + "\n")


def run_pipeline_cycle(config: dict, db: DatabaseManager, collector: FacebookCollector, evaluator: DealEvaluator, notifier: TelegramNotifier, discord_notifier: DiscordNotifier = None) -> None:
    """Execute one complete scraping, filtering, cognitive evaluation, and notification cycle."""
    logger.info("=" * 70)
    logger.info(f"Starting FacebookSnoof execution cycle at {datetime.now().isoformat()}")
    logger.info("=" * 70)

    groups = config.get("groups", [])
    if not groups:
        logger.warning("No monitored groups configured in config.yaml.")
        return

    db.sync_monitored_groups(groups)
    min_alert_score = config.get("gemini", {}).get("min_deal_score_alert", 75)

    cycle_results = []
    total_scraped = 0
    total_phase1_passed = 0
    total_interesting = 0
    total_skipped = 0

    for group in groups:
        group_id = str(group["id"])
        group_name = group.get("name", f"Group {group_id}")

        logger.info(f"Processing group: [{group_name}] ({group_id})...")
        raw_posts = collector.scrape_group(group_id, group_name, discord_notifier)
        db.update_group_last_scraped(group_id)

        for post in raw_posts:
            total_scraped += 1
            post_id = str(post["post_id"])
            post_text = post.get("post_text", "")
            post_url = post.get("post_url", "")
            author_name = post.get("author_name", "Unknown")

            # Deduplication check
            if db.post_exists(post_id):
                logger.debug(f"Post {post_id} already exists in database. Skipping.")
                continue

            # Tier 1: Intent & Noise Filter (Hanya postingan gagal Phase 1 yang dibuang total)
            is_valid_candidate = is_candidate_listing(post_text)
            db.insert_post(
                post_id=post_id,
                group_id=group_id,
                post_url=post_url,
                post_text=post_text,
                author_name=author_name
            )

            if not is_valid_candidate:
                logger.debug(f"Post {post_id} dropped by Tier-1 Regex Filter (non-sale / WTB / Ask).")
                continue

            total_phase1_passed += 1
            logger.info(f"Tier-1 Candidate Passed! Evaluating post {post_id} with Ollama...")

            # Tier 2: Ollama Cognitive Valuation
            eval_result = evaluator.evaluate_post(post_text)
            if not eval_result:
                logger.warning(f"Evaluation failed or yielded invalid JSON for post {post_id}.")
                continue

            is_interesting = eval_result.is_valid_pc_hardware and (eval_result.deal_score >= min_alert_score)

            if is_interesting:
                total_interesting += 1
            else:
                total_skipped += 1

            # Save evaluation result to database if valid hardware
            eval_id = None
            if eval_result.is_valid_pc_hardware:
                eval_id = db.save_deal_evaluation(
                    post_id=post_id,
                    hardware_name=eval_result.hardware_name,
                    item_category=eval_result.item_category,
                    asking_price=eval_result.asking_price,
                    estimated_market_price=eval_result.estimated_market_price,
                    condition_summary=eval_result.condition,
                    deal_score=eval_result.deal_score,
                    verdict=eval_result.verdict
                )

            # Store result for final end-of-cycle summary report
            cycle_results.append({
                "post_id": post_id,
                "group_name": group_name,
                "post_url": post_url,
                "hardware_name": eval_result.hardware_name if eval_result.is_valid_pc_hardware else "Non-PC Hardware Core",
                "asking_price": eval_result.asking_price,
                "estimated_market_price": eval_result.estimated_market_price,
                "deal_score": eval_result.deal_score,
                "verdict": eval_result.verdict,
                "reasoning": eval_result.reasoning if eval_result.reasoning else "Tidak memenuhi kriteria deal menarik.",
                "is_valid_pc_hardware": eval_result.is_valid_pc_hardware,
                "is_interesting": is_interesting
            })

            # Telegram & Discord alert dispatch for all Phase 1 passed posts
            if is_interesting:
                sent_tg = notifier.send_deal_alert(
                    hardware_name=eval_result.hardware_name,
                    asking_price=eval_result.asking_price,
                    estimated_market_price=eval_result.estimated_market_price,
                    deal_score=eval_result.deal_score,
                    verdict=eval_result.verdict,
                    condition=eval_result.condition,
                    reasoning=eval_result.reasoning,
                    post_url=post_url,
                    group_name=group_name
                )
                if discord_notifier:
                    discord_notifier.send_deal_alert(
                        hardware_name=eval_result.hardware_name,
                        asking_price=eval_result.asking_price,
                        estimated_market_price=eval_result.estimated_market_price,
                        deal_score=eval_result.deal_score,
                        verdict=eval_result.verdict,
                        condition=eval_result.condition,
                        reasoning=eval_result.reasoning,
                        post_url=post_url,
                        group_name=group_name
                    )
                if sent_tg and eval_id:
                    db.mark_as_notified(eval_id)
            else:
                # Dispatch subtle grey skipped embed for Phase-1 passed skipped posts
                if discord_notifier:
                    discord_notifier.send_skipped_alert(
                        hardware_name=eval_result.hardware_name if eval_result.is_valid_pc_hardware else "Non-PC Hardware Core",
                        asking_price=eval_result.asking_price,
                        estimated_market_price=eval_result.estimated_market_price,
                        deal_score=eval_result.deal_score,
                        verdict=eval_result.verdict,
                        reasoning=eval_result.reasoning if eval_result.reasoning else "Tidak memenuhi kriteria deal menarik.",
                        post_url=post_url,
                        group_name=group_name,
                        is_valid_pc_hardware=eval_result.is_valid_pc_hardware
                    )

    # Print clean human-intuitive summary report AFTER all groups are scraped
    print_cycle_summary_report(cycle_results, total_scraped, total_phase1_passed, total_interesting, total_skipped)
    logger.info("FacebookSnoof cycle complete.\n")


def main():
    parser = argparse.ArgumentParser(description="FacebookSnoof Scraper & Cognitive Evaluator Daemon")
    parser.add_argument("--single-run", action="store_true", help="Run a single pipeline cycle and exit immediately.")
    parser.add_argument("--config", default="config/config.yaml", help="Path to YAML configuration file.")
    args = parser.parse_args()

    os.makedirs("logs", exist_ok=True)
    config = load_config(args.config)

    # Initialize sub-systems
    db = DatabaseManager()
    
    collector_cfg = config.get("scraper", {})
    collector = FacebookCollector(
        storage_state_path=collector_cfg.get("storage_state_path", "config/storage_state.json"),
        headless=collector_cfg.get("headless", True),
        max_scrolls=collector_cfg.get("max_scrolls_per_group", 4),
        delay_min=collector_cfg.get("request_delay_min_seconds", 5.0),
        delay_max=collector_cfg.get("request_delay_max_seconds", 12.0)
    )

    min_alert_score = config.get("gemini", {}).get("min_deal_score_alert", 75)
    gemini_cfg = config.get("gemini", {})
    evaluator = DealEvaluator(
        api_key=gemini_cfg.get("api_key", ""),
        primary_model=gemini_cfg.get("primary_model", "gemini-2.5-flash-lite"),
        fallback_model=gemini_cfg.get("fallback_model", "gemini-2.0-flash"),
        timeout_seconds=gemini_cfg.get("timeout_seconds", 30),
        lookup_table_path=gemini_cfg.get("lookup_table_path", "lookup_table.md")
    )

    telegram_cfg = config.get("telegram", {})
    notifier = TelegramNotifier(
        bot_token=telegram_cfg.get("bot_token", ""),
        chat_id=telegram_cfg.get("chat_id", ""),
        enabled=telegram_cfg.get("enabled", False)
    )

    discord_cfg = config.get("discord", {})
    discord_notifier = DiscordNotifier(
        webhook_url=discord_cfg.get("webhook_url", ""),
        enabled=discord_cfg.get("enabled", False)
    )

    # Launch background Discord Command Listener if bot_token is configured
    start_discord_command_listener(discord_cfg.get("bot_token", ""), discord_cfg.get("webhook_url", ""))

    if args.single_run:
        logger.info("Executing single pipeline run mode...")
        run_pipeline_cycle(config, db, collector, evaluator, notifier, discord_notifier)
        sys.exit(0)

    # APScheduler Background Execution Mode
    interval_minutes = collector_cfg.get("schedule_interval_minutes", 60)
    jitter_minutes = collector_cfg.get("schedule_jitter_minutes", 15)

    scheduler = BlockingScheduler()
    scheduler.add_job(
        func=run_pipeline_cycle,
        trigger="interval",
        minutes=interval_minutes,
        jitter=jitter_minutes * 60,
        args=[config, db, collector, evaluator, notifier, discord_notifier],
        next_run_time=datetime.now()  # Run immediately on start
    )

    logger.info(f"FacebookSnoof daemon starting. Interval: {interval_minutes}m (jitter: ±{jitter_minutes}m)... Press Ctrl+C to stop.")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("FacebookSnoof daemon stopped cleanly.")


if __name__ == "__main__":
    main()
