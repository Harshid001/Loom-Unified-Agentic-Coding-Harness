from loom.integrations.ci_bot import (
    CIBot,
    CIBotConfig,
    CIBotProvider,
)
from loom.integrations.slack import (
    SlackNotification,
    SlackNotificationLevel,
    SlackNotificationTemplate,
    SlackNotifier,
)


class TestCIBotTriage:
    def test_triage_matches_bug_labels(self):
        config = CIBotConfig(provider=CIBotProvider.GITHUB, org_id="org_1", repo_full_name="acme/widgets", api_base_url="")
        bot = CIBot(config)
        assert bot.should_triage_issue("Fix login bug", ["bug"])
        assert bot.should_triage_issue("Fix login bug", ["loom:auto-fix"])

    def test_triage_matches_title_keywords(self):
        config = CIBotConfig(provider=CIBotProvider.GITHUB, org_id="org_1", repo_full_name="a/b", api_base_url="")
        bot = CIBot(config)
        assert bot.should_triage_issue("fix the crashing login", [])
        assert bot.should_triage_issue("security vulnerability in auth", [])
        assert bot.should_triage_issue("broken pipeline", [])

    def test_triage_ignores_feature_requests(self):
        config = CIBotConfig(provider=CIBotProvider.GITHUB, org_id="org_1", repo_full_name="a/b", api_base_url="")
        bot = CIBot(config)
        assert not bot.should_triage_issue("Add new feature X", [])

    def test_disabled_bot_never_triages(self):
        config = CIBotConfig(provider=CIBotProvider.GITHUB, org_id="org_1", repo_full_name="a/b", api_base_url="", enabled=False)
        bot = CIBot(config)
        assert not bot.should_triage_issue("fix bug", ["bug"])


class TestCIBotBranchNaming:
    def test_branch_name_sanitization(self):
        config = CIBotConfig(provider=CIBotProvider.GITHUB, org_id="org_1", repo_full_name="a/b", api_base_url="")
        bot = CIBot(config)
        branch = bot.build_verification_branch_name("Fix: login crash & burn!!!", 42)
        assert branch.startswith("loom/fix/42-")
        assert "!" not in branch

    def test_long_title_truncates(self):
        config = CIBotConfig(provider=CIBotProvider.GITHUB, org_id="org_1", repo_full_name="a/b", api_base_url="")
        bot = CIBot(config)
        branch = bot.build_verification_branch_name("A" * 100, 1)
        assert len(branch) <= 60


class TestCIBotPRGeneration:
    def test_generate_pr_template_data(self):
        config = CIBotConfig(provider=CIBotProvider.GITHUB, org_id="org_1", repo_full_name="a/b", api_base_url="https://loom.example.com")
        bot = CIBot(config)
        data = bot.generate_pr_template_data("run_abc", "Fix crash", 42, "diff", 0.97, True, 0.05, 3, "claude-3")
        assert data.run_id == "run_abc"
        assert data.confidence_score == 0.97

    def test_prepare_pr_standard(self):
        config = CIBotConfig(provider=CIBotProvider.GITHUB, org_id="o", repo_full_name="a/b", api_base_url="")
        bot = CIBot(config)
        data = bot.generate_pr_template_data("r", "fix", 1, "diff", 0.97, True, model_used="claude")
        pr = bot.prepare_pr(data)
        assert pr["action"] == "prepared"
        assert "Loom Automated Fix" in pr["body"]

    def test_prepare_pr_disabled_skips(self):
        config = CIBotConfig(provider=CIBotProvider.GITHUB, org_id="o", repo_full_name="a/b", api_base_url="", enabled=False)
        bot = CIBot(config)
        data = bot.generate_pr_template_data("r", "fix", 1, "", 0.5, False)
        pr = bot.prepare_pr(data)
        assert pr["action"] == "skipped"

    def test_max_open_prs_exceeded(self):
        config = CIBotConfig(provider=CIBotProvider.GITHUB, org_id="o", repo_full_name="a/b", api_base_url="", max_open_prs=1)
        bot = CIBot(config)
        data = bot.generate_pr_template_data("r", "fix", 1, "", 0.5, False)
        bot.prepare_pr(data)
        pr = bot.prepare_pr(data)
        assert pr["action"] == "skipped"


class TestCIBotFalseTrigger:
    def test_initial_rate_zero(self):
        config = CIBotConfig(provider=CIBotProvider.GITHUB, org_id="o", repo_full_name="a/b", api_base_url="")
        bot = CIBot(config)
        assert bot.false_trigger_rate == 0.0

    def test_mixed_triggers(self):
        config = CIBotConfig(provider=CIBotProvider.GITHUB, org_id="o", repo_full_name="a/b", api_base_url="")
        bot = CIBot(config)
        bot.record_trigger_result(was_correct_fix=True)
        bot.record_trigger_result(was_correct_fix=False)
        assert bot.false_trigger_rate == 0.5

    def test_reset_stats(self):
        config = CIBotConfig(provider=CIBotProvider.GITHUB, org_id="o", repo_full_name="a/b", api_base_url="")
        bot = CIBot(config)
        bot.record_trigger_result(was_correct_fix=False)
        bot.reset_stats()
        assert bot.false_trigger_rate == 0.0


class TestCIBotCommitMessage:
    def test_format(self):
        config = CIBotConfig(provider=CIBotProvider.GITHUB, org_id="o", repo_full_name="a/b", api_base_url="")
        bot = CIBot(config)
        msg = bot.build_commit_message("run_1", "Fix crash", 0.95)
        assert "Fix crash" in msg
        assert "run_1" in msg


class TestCIBotSerialize:
    def test_serialize_stats(self):
        config = CIBotConfig(provider=CIBotProvider.GITHUB, org_id="o", repo_full_name="a/b", api_base_url="")
        bot = CIBot(config)
        bot.record_trigger_result(was_correct_fix=True)
        s = bot.serialize()
        assert s["provider"] == "github"
        assert s["enabled"] is True


class TestSlackNotifications:
    def test_run_completed(self):
        notifier = SlackNotifier(webhook_url="https://hooks.slack.com/test")
        n = notifier.build_run_completed_notification("run_x", "Fix crash", "a/b", 0.95, 0.05, True, "claude")
        assert n.level == SlackNotificationLevel.SUCCESS
        assert "run_x" in n.title

    def test_run_failed(self):
        notifier = SlackNotifier(webhook_url="https://hooks.slack.com/test")
        n = notifier.build_failed_notification("run_y", "a/b", "Fix auth", "null pointer", "patcher")
        assert n.level == SlackNotificationLevel.ERROR
        assert n.run_id == "run_y"

    def test_security_hold(self):
        notifier = SlackNotifier(webhook_url="https://hooks.slack.com/test")
        n = notifier.build_security_hold_notification("run_z", "a/b", ["src/auth/login.py"], "Sensitive")
        assert n.template == SlackNotificationTemplate.SECURITY_HOLD

    def test_quota_warning(self):
        notifier = SlackNotifier(webhook_url="https://hooks.slack.com/test")
        n = notifier.build_quota_warning_notification("org_1", 85.0, 425, 500)
        assert n.template == SlackNotificationTemplate.QUOTA_WARNING

    def test_quota_exceeded_hard_stop(self):
        notifier = SlackNotifier(webhook_url="https://hooks.slack.com/test")
        n = notifier.build_quota_exceeded_notification("org_1", 110.0, 550, 500, hard_stop_triggered=True)
        assert n.level == SlackNotificationLevel.CRITICAL

    def test_merged(self):
        notifier = SlackNotifier(webhook_url="https://hooks.slack.com/test")
        n = notifier.build_merged_notification("run_m", "a/b", "Fix", 0.98)
        assert n.template == SlackNotificationTemplate.MERGED

    def test_rolled_back(self):
        notifier = SlackNotifier(webhook_url="https://hooks.slack.com/test")
        n = notifier.build_rolled_back_notification("run_rb", "a/b", "Fix", "CI failure")
        assert n.template == SlackNotificationTemplate.ROLLED_BACK
        assert "CI failure" in n.body

    def test_payload_structure(self):
        notifier = SlackNotifier(webhook_url="https://hooks.slack.com/test", bot_name="LoomBot")
        notification = SlackNotification(title="T", body="B", level=SlackNotificationLevel.INFO)
        payload = notifier._build_payload(notification)
        assert payload["username"] == "LoomBot"
        assert len(payload["attachments"]) == 1

    def test_channel_override(self):
        notifier = SlackNotifier(webhook_url="https://hooks.slack.com/test", channel_override="#alerts")
        notification = SlackNotification(title="T", body="B")
        payload = notifier._build_payload(notification)
        assert payload["channel"] == "#alerts"
