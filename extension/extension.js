'use strict';

const ByteArray = imports.byteArray;
const Cairo = imports.cairo;
const { Clutter, Gio, GLib, GObject, St } = imports.gi;
const Main = imports.ui.main;
const PanelMenu = imports.ui.panelMenu;
const PopupMenu = imports.ui.popupMenu;

const UUID = 'ai-token-bars@fen22.github.io';
const CODEX_DB = GLib.build_filenamev([GLib.get_home_dir(), '.codex', 'state_5.sqlite']);
const CLAUDE_STATUS = GLib.build_filenamev([GLib.get_home_dir(), '.cache', 'claude-token-bar', 'status.json']);
const SQLITE = '/usr/bin/sqlite3';
const TAIL = '/usr/bin/tail';
const REFRESH_SECONDS = 10;
const CODEX_BAR_WIDTH = 86;
const CLAUDE_BAR_WIDTH = 86;
const BAR_HEIGHT = 7;
const CLAUDE_STALE_SECONDS = 120;

const COLORS = {
    codex: [0.34, 0.78, 0.52, 1],
    warning: [0.96, 0.77, 0.26, 1],
    danger: [1.0, 0.42, 0.42, 1],
    claude: [0.88, 0.42, 0.18, 1],
    track: [1, 1, 1, 0.22],
};

function formatPercent(value) {
    if (!Number.isFinite(value))
        return 'unknown';

    return `${Math.round(value)}%`;
}

function formatDuration(seconds) {
    if (!Number.isFinite(seconds))
        return 'unknown';

    if (seconds <= 0)
        return 'now';

    let days = Math.floor(seconds / 86400);
    let hours = Math.floor((seconds % 86400) / 3600);
    let minutes = Math.floor((seconds % 3600) / 60);

    if (days > 0)
        return `${days}d ${hours}h`;

    if (hours > 0)
        return `${hours}h ${minutes}m`;

    return `${minutes}m`;
}

function formatTime(epochSeconds) {
    if (!epochSeconds)
        return 'unknown';

    let date = GLib.DateTime.new_from_unix_local(epochSeconds);
    return date ? date.format('%Y-%m-%d %H:%M:%S') : 'unknown';
}

function clamp(value, min, max) {
    return Math.min(Math.max(value, min), max);
}

function numberFrom(value) {
    let number = Number.parseFloat(value);
    return Number.isFinite(number) ? number : NaN;
}

function intFrom(value) {
    let number = Number.parseInt(value);
    return Number.isFinite(number) ? number : 0;
}

function runCommand(argv) {
    let proc = Gio.Subprocess.new(
        argv,
        Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_PIPE
    );
    let [, stdout, stderr] = proc.communicate_utf8(null, null);

    if (proc.get_exit_status() !== 0)
        throw new Error((stderr || `${argv[0]} failed`).trim());

    return (stdout || '').trim();
}

function runSql(query) {
    return runCommand([SQLITE, '-readonly', '-separator', '\t', CODEX_DB, query]);
}

function firstLineFields(output) {
    let line = output.split('\n')[0] || '';
    return line.split('\t');
}

function readJsonFile(path) {
    if (!GLib.file_test(path, GLib.FileTest.EXISTS))
        throw new Error(`${path} does not exist`);

    let [ok, bytes] = GLib.file_get_contents(path);

    if (!ok)
        throw new Error(`Could not read ${path}`);

    return JSON.parse(ByteArray.toString(bytes));
}

function latestTokenCountFromRollout(path) {
    let output = runCommand([TAIL, '-n', '500', path]);
    let lines = output.split('\n');

    for (let i = lines.length - 1; i >= 0; i--) {
        let line = lines[i];

        if (line.indexOf('"token_count"') === -1)
            continue;

        try {
            let parsed = JSON.parse(line);
            let payload = parsed.payload || {};

            if (parsed.type === 'event_msg' && payload.type === 'token_count')
                return payload;
        } catch (error) {
            log(`[${UUID}] failed to parse token_count line: ${error.message}`);
        }
    }

    throw new Error(`No token_count event found in ${path}`);
}

function roundedRect(cr, x, y, width, height, radius) {
    let r = Math.min(radius, width / 2, height / 2);

    cr.newSubPath();
    cr.arc(x + width - r, y + r, r, -Math.PI / 2, 0);
    cr.arc(x + width - r, y + height - r, r, 0, Math.PI / 2);
    cr.arc(x + r, y + height - r, r, Math.PI / 2, Math.PI);
    cr.arc(x + r, y + r, r, Math.PI, Math.PI * 1.5);
    cr.closePath();
}

function setSource(cr, color) {
    cr.setSourceRGBA(color[0], color[1], color[2], color[3]);
}

function createProgressBar(width, color) {
    let bar = new St.DrawingArea({
        style_class: 'ai-token-progress',
        y_align: Clutter.ActorAlign.CENTER,
    });
    bar.set_size(width, BAR_HEIGHT);
    bar._percent = 0;
    bar._fillColor = color;

    bar.connect('repaint', area => {
        let cr = area.get_context();
        let [surfaceWidth, surfaceHeight] = area.get_surface_size();
        let y = Math.floor((surfaceHeight - BAR_HEIGHT) / 2);
        let fillWidth = Math.round(surfaceWidth * clamp(area._percent, 0, 1));

        setSource(cr, COLORS.track);
        roundedRect(cr, 0, y, surfaceWidth, BAR_HEIGHT, BAR_HEIGHT / 2);
        cr.fill();

        if (fillWidth > 0) {
            setSource(cr, area._fillColor);
            roundedRect(cr, 0, y, fillWidth, BAR_HEIGHT, BAR_HEIGHT / 2);
            cr.fill();
        }

        if (cr.$dispose)
            cr.$dispose();
    });

    return { actor: bar, width };
}

function createCodexIcon() {
    let icon = new St.DrawingArea({
        style_class: 'codex-token-icon',
        y_align: Clutter.ActorAlign.CENTER,
    });
    icon.set_size(16, 16);

    icon.connect('repaint', area => {
        let cr = area.get_context();
        let [width, height] = area.get_surface_size();
        let cx = width / 2;
        let cy = height / 2;
        let radius = Math.min(width, height) * 0.39;

        cr.setSourceRGBA(1, 1, 1, 0.95);
        cr.setLineWidth(1.35);

        for (let i = 0; i < 6; i++) {
            let angle = -Math.PI / 2 + i * Math.PI / 3;
            let x = cx + Math.cos(angle) * radius;
            let y = cy + Math.sin(angle) * radius;

            if (i === 0)
                cr.moveTo(x, y);
            else
                cr.lineTo(x, y);
        }

        cr.closePath();
        cr.stroke();

        cr.setLineWidth(1.8);
        cr.arc(cx + 0.9, cy, radius * 0.48, Math.PI * 0.28, Math.PI * 1.72);
        cr.stroke();

        if (cr.$dispose)
            cr.$dispose();
    });

    return icon;
}

function createClaudeIcon() {
    let icon = new St.DrawingArea({
        style_class: 'claude-token-icon',
        y_align: Clutter.ActorAlign.CENTER,
    });
    icon.set_size(16, 16);

    icon.connect('repaint', area => {
        let cr = area.get_context();
        let [width, height] = area.get_surface_size();
        let cx = width / 2;
        let cy = height / 2;
        let radius = Math.min(width, height) * 0.43;

        setSource(cr, COLORS.claude);
        cr.arc(cx, cy, radius, 0, Math.PI * 2);
        cr.fill();

        cr.setSourceRGBA(1, 1, 1, 0.95);
        cr.setLineWidth(1.7);
        cr.arc(cx + 0.9, cy, radius * 0.52, Math.PI * 0.28, Math.PI * 1.72);
        cr.stroke();

        if (cr.$dispose)
            cr.$dispose();
    });

    return icon;
}

function createSourceGroup(icon, progressActor) {
    let group = new St.BoxLayout({
        style_class: 'ai-token-source',
        y_align: Clutter.ActorAlign.CENTER,
    });
    group.add_child(icon);
    group.add_child(progressActor);
    return group;
}

const AITokenBars = GObject.registerClass(
class AITokenBars extends PanelMenu.Button {
    _init() {
        super._init(0.0, 'AI Token Bars', false);

        this._timeoutId = 0;

        this._box = new St.BoxLayout({
            style_class: 'ai-token-panel',
            y_align: Clutter.ActorAlign.CENTER,
        });

        this._codexBar = createProgressBar(CODEX_BAR_WIDTH, COLORS.codex);
        this._claudeBar = createProgressBar(CLAUDE_BAR_WIDTH, COLORS.claude);

        this._box.add_child(createSourceGroup(createCodexIcon(), this._codexBar.actor));
        this._box.add_child(createSourceGroup(createClaudeIcon(), this._claudeBar.actor));
        this.add_child(this._box);

        this._codexStatusItem = new PopupMenu.PopupMenuItem('Loading Codex limit usage...', {
            reactive: false,
        });
        this._codexPrimaryItem = new PopupMenu.PopupMenuItem('', { reactive: false });
        this._codexSecondaryItem = new PopupMenu.PopupMenuItem('', { reactive: false });
        this._codexUpdatedItem = new PopupMenu.PopupMenuItem('', { reactive: false });

        this._claudeStatusItem = new PopupMenu.PopupMenuItem('Loading Claude limit usage...', {
            reactive: false,
        });
        this._claudeFiveHourItem = new PopupMenu.PopupMenuItem('', { reactive: false });
        this._claudeWeeklyItem = new PopupMenu.PopupMenuItem('', { reactive: false });
        this._claudeContextItem = new PopupMenu.PopupMenuItem('', { reactive: false });
        this._claudeUpdatedItem = new PopupMenu.PopupMenuItem('', { reactive: false });

        this._refreshItem = new PopupMenu.PopupMenuItem('Refresh now');

        this.menu.addMenuItem(this._codexStatusItem);
        this.menu.addMenuItem(this._codexPrimaryItem);
        this.menu.addMenuItem(this._codexSecondaryItem);
        this.menu.addMenuItem(this._codexUpdatedItem);
        this.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());
        this.menu.addMenuItem(this._claudeStatusItem);
        this.menu.addMenuItem(this._claudeFiveHourItem);
        this.menu.addMenuItem(this._claudeWeeklyItem);
        this.menu.addMenuItem(this._claudeContextItem);
        this.menu.addMenuItem(this._claudeUpdatedItem);
        this.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());
        this.menu.addMenuItem(this._refreshItem);

        this._refreshItem.connect('activate', () => this._refresh());

        this._refresh();
        this._timeoutId = GLib.timeout_add_seconds(
            GLib.PRIORITY_DEFAULT,
            REFRESH_SECONDS,
            () => {
                this._refresh();
                return GLib.SOURCE_CONTINUE;
            }
        );
    }

    destroy() {
        if (this._timeoutId) {
            GLib.Source.remove(this._timeoutId);
            this._timeoutId = 0;
        }

        super.destroy();
    }

    _refresh() {
        this._refreshCodex();
        this._refreshClaude();
    }

    _refreshCodex() {
        try {
            if (!GLib.file_test(CODEX_DB, GLib.FileTest.EXISTS))
                throw new Error(`${CODEX_DB} does not exist`);

            let latest = firstLineFields(runSql(
                "select rollout_path, replace(coalesce(nullif(title,''),'Untitled'), char(10), ' '), updated_at " +
                "from threads where archived = 0 order by updated_at desc limit 1;"
            ));

            let rolloutPath = latest[0] || '';
            let title = latest[1] || 'Untitled';
            let updatedAt = intFrom(latest[2] || '0');

            if (!rolloutPath)
                throw new Error('Latest Codex thread has no rollout path');

            let tokenCount = latestTokenCountFromRollout(rolloutPath);
            let rateLimits = tokenCount.rate_limits || {};
            let primary = rateLimits.primary || {};
            let secondary = rateLimits.secondary || {};

            let usedPercent = numberFrom(primary.used_percent);
            let leftPercent = Number.isFinite(usedPercent) ? Math.max(0, 100 - usedPercent) : NaN;
            let resetAt = intFrom(primary.resets_at || '0');
            let resetIn = resetAt ? resetAt - GLib.DateTime.new_now_local().to_unix() : NaN;

            this._setBar(this._codexBar, usedPercent, this._codexColorFor(usedPercent));
            this._codexStatusItem.label.set_text(`Codex: ${formatPercent(usedPercent)} used, ${formatPercent(leftPercent)} left`);
            this._codexPrimaryItem.label.set_text(
                `Primary window: ${formatPercent(usedPercent)} used / ${formatPercent(leftPercent)} left (${primary.window_minutes || '?'} min)`
            );
            this._codexSecondaryItem.label.set_text(
                `Weekly window: ${formatPercent(numberFrom(secondary.used_percent))} used (${secondary.window_minutes || '?'} min)`
            );
            this._codexUpdatedItem.label.set_text(
                `Resets in ${formatDuration(resetIn)} at ${formatTime(resetAt)} · ${title} · updated ${formatTime(updatedAt)}`
            );
        } catch (error) {
            log(`[${UUID}] Codex: ${error.message}`);
            this._setBar(this._codexBar, 0, COLORS.codex);
            this._codexStatusItem.label.set_text(`Codex usage unavailable: ${error.message}`);
            this._codexPrimaryItem.label.set_text('');
            this._codexSecondaryItem.label.set_text('');
            this._codexUpdatedItem.label.set_text('');
        }
    }

    _refreshClaude() {
        try {
            let status = readJsonFile(CLAUDE_STATUS);
            let now = GLib.DateTime.new_now_local().to_unix();
            let updatedAt = intFrom(status.updated_at);
            let age = updatedAt ? now - updatedAt : NaN;
            let stale = Number.isFinite(age) && age > CLAUDE_STALE_SECONDS;
            let rateLimits = status.rate_limits || {};
            let fiveHour = rateLimits.five_hour || {};
            let weekly = rateLimits.seven_day || {};
            let context = status.context_window || {};
            let model = status.model || {};

            let fiveHourUsed = numberFrom(fiveHour.used_percentage);
            let contextUsed = numberFrom(context.used_percentage);
            let usedPercent = Number.isFinite(fiveHourUsed) ? fiveHourUsed : contextUsed;
            let source = Number.isFinite(fiveHourUsed) ? '5-hour limit' : 'context window';
            let leftPercent = Number.isFinite(usedPercent) ? Math.max(0, 100 - usedPercent) : NaN;
            let resetAt = intFrom(fiveHour.resets_at);
            let resetIn = resetAt ? resetAt - now : NaN;
            let weeklyResetAt = intFrom(weekly.resets_at);

            this._setBar(this._claudeBar, usedPercent, COLORS.claude);

            let freshness = stale ? ` · stale ${formatDuration(age)} old` : '';
            this._claudeStatusItem.label.set_text(
                `Claude: ${formatPercent(usedPercent)} used, ${formatPercent(leftPercent)} left (${source})${freshness}`
            );
            this._claudeFiveHourItem.label.set_text(
                Number.isFinite(fiveHourUsed)
                    ? `5-hour window: ${formatPercent(fiveHourUsed)} used / ${formatPercent(Math.max(0, 100 - fiveHourUsed))} left · resets in ${formatDuration(resetIn)} at ${formatTime(resetAt)}`
                    : '5-hour window: unavailable until Claude Code reports subscription limits'
            );
            this._claudeWeeklyItem.label.set_text(
                Number.isFinite(numberFrom(weekly.used_percentage))
                    ? `Weekly window: ${formatPercent(numberFrom(weekly.used_percentage))} used · resets at ${formatTime(weeklyResetAt)}`
                    : 'Weekly window: unavailable'
            );
            this._claudeContextItem.label.set_text(
                Number.isFinite(contextUsed)
                    ? `Context window: ${formatPercent(contextUsed)} used / ${formatPercent(Math.max(0, 100 - contextUsed))} left`
                    : 'Context window: unavailable'
            );
            this._claudeUpdatedItem.label.set_text(
                `${model.display_name || model.id || 'Claude Code'} · updated ${formatTime(updatedAt)}`
            );
        } catch (error) {
            log(`[${UUID}] Claude: ${error.message}`);
            this._setBar(this._claudeBar, 0, COLORS.claude);
            this._claudeStatusItem.label.set_text('Claude usage unavailable: start Claude Code and send one prompt');
            this._claudeFiveHourItem.label.set_text(error.message);
            this._claudeWeeklyItem.label.set_text('');
            this._claudeContextItem.label.set_text('');
            this._claudeUpdatedItem.label.set_text('');
        }
    }

    _setBar(bar, usedPercent, color) {
        let percent = Number.isFinite(usedPercent) ? clamp(usedPercent / 100, 0, 1) : 0;
        bar.actor._percent = percent;
        bar.actor._fillColor = color;
        bar.actor.queue_repaint();
    }

    _codexColorFor(usedPercent) {
        if (!Number.isFinite(usedPercent))
            return COLORS.codex;

        if (usedPercent >= 90)
            return COLORS.danger;

        if (usedPercent >= 70)
            return COLORS.warning;

        return COLORS.codex;
    }
});

let indicator = null;

function init() {
}

function enable() {
    indicator = new AITokenBars();
    Main.panel.addToStatusArea(UUID, indicator);
}

function disable() {
    if (indicator) {
        indicator.destroy();
        indicator = null;
    }
}
