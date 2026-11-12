<?php
// Shared bootstrap for the CLI scripts: boots the Castopod app at --app so its models,
// entities and database configuration are used as-is.
declare(strict_types=1);

use CodeIgniter\Boot;
use Config\Paths;

function cp_boot(string $appPath): void
{
    $appPath = realpath($appPath);
    if ($appPath === false || ! is_dir($appPath . '/app') || ! is_dir($appPath . '/public')) {
        fwrite(STDERR, "Not a Castopod install: {$appPath}\n");
        exit(1);
    }
    if (! defined('FCPATH')) {
        define('FCPATH', $appPath . '/public' . DIRECTORY_SEPARATOR);
    }
    chdir(FCPATH);
    require $appPath . '/app/Config/Paths.php';
    $paths = new Paths();
    require $paths->systemDirectory . '/Boot.php';
    if (! defined('ENVIRONMENT')) {
        define('ENVIRONMENT', getenv('CI_ENVIRONMENT') ?: 'production');
    }
    Boot::bootConsole($paths);
    // web controllers load helpers (media, auth, ...) that model callbacks rely on; load them all here
    foreach (array_merge(glob($appPath . '/app/Helpers/*_helper.php') ?: [], glob($appPath . '/modules/*/Helpers/*_helper.php') ?: []) as $h) {
        require_once $h;
    }
}

function cp_opt(array $opts, string $key, ?string $default = null, bool $required = false): ?string
{
    $v = $opts[$key] ?? $default;
    if ($required && ($v === null || $v === '')) {
        fwrite(STDERR, "Missing --{$key}\n");
        exit(1);
    }
    return $v === null ? null : (string) $v;
}

// Shared read-only snapshot, also used under the mutation lock for conditional updates.
function cp_episode_snapshot($e): array
{
    return [
        'id' => (int) $e->id, 'slug' => $e->slug, 'title' => $e->title, 'guid' => $e->guid,
        'status' => $e->publication_status === 'not_published' ? 'draft' : $e->publication_status,
        'published_at' => (string) $e->published_at,
        'description_sha256' => hash('sha256', (string) $e->description_markdown),
        'description_markdown' => (string) $e->description_markdown,
        'audio_url' => $e->audio_url, 'audio_file_key' => $e->getAudio()->file_key,
        'audio_file_size' => (int) $e->getAudio()->file_size,
        'duration' => (float) $e->getAudio()->duration, 'link' => $e->link,
        'number' => $e->number, 'season' => $e->season_number,
        'transcript_id' => $e->transcript_id,
        'transcript_url' => $e->getTranscript()?->file_url ?? $e->transcript_remote_url,
        'transcript_json_url' => $e->getTranscript()?->json_url,
        'chapters_id' => $e->chapters_id,
        'chapters_url' => $e->getChapters()?->file_url ?? $e->chapters_remote_url,
    ];
}

// Coordinate cooperating clients on different machines before reading/mutating an episode.
function cp_episode_lock(string $app, string $podcast, string $slug)
{
    $app = realpath($app);
    if ($app === false) { throw new RuntimeException('Application path does not exist'); }
    $root = $app . '/writable/sovereign-podcaster-locks';
    if (is_link($root) || (!is_dir($root) && !mkdir($root, 0700) && !is_dir($root))) {
        throw new RuntimeException('Cannot create private episode lock directory');
    }
    if ((fileperms($root) & 0777) !== 0700 || fileowner($root) !== posix_geteuid()) {
        throw new RuntimeException('Episode lock directory must be private and owned by the service user');
    }
    $path = $root . '/' . hash('sha256', $podcast . "\0" . $slug) . '.lock';
    if (is_link($path)) { throw new RuntimeException('Lock symlink refused'); }
    $lock = fopen($path, 'c');
    if ($lock === false || !chmod($path, 0600) || !flock($lock, LOCK_EX | LOCK_NB)) {
        throw new RuntimeException('Another operation is working on this episode');
    }
    return $lock; // Hold this resource until the helper exits.
}
