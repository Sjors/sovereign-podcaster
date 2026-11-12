#!/usr/bin/env php
<?php
// Read-only discovery/readback. Query the model directly so drafts are included.
declare(strict_types=1);
require __DIR__ . '/castopod-bootstrap.php';
$o = getopt('', ['app:', 'podcast:', 'slug:', 'user:']);
cp_boot(cp_opt($o, 'app', null, true));

use App\Models\EpisodeModel;
use App\Models\PodcastModel;
use Modules\Auth\Models\UserModel;

$result = ['version' => CP_VERSION, 'helper_api' => 1, 'features' => ['chapters', 'conditional-update', 'episode-number']];
if (isset($o['user'])) {
    $user = (new UserModel())->where('username', $o['user'])->first();
    $result['user_exists'] = $user !== null;
}
if (! isset($o['podcast'])) {
    $result['podcasts'] = array_map(static fn ($p) => [
        'id' => (int) $p->id, 'handle' => $p->handle, 'title' => $p->title,
        'status' => $p->publication_status,
    ], (new PodcastModel())->findAll());
} else {
    $podcast = (new PodcastModel())->getPodcastByHandle($o['podcast']);
    if ($podcast === null) { fwrite(STDERR, "Podcast not found\n"); exit(1); }
    $result['podcast'] = ['id' => (int) $podcast->id, 'handle' => $podcast->handle,
        'title' => $podcast->title, 'status' => $podcast->publication_status];
    if (isset($o['slug'])) {
        $e = (new EpisodeModel())->where(['podcast_id' => $podcast->id, 'slug' => $o['slug']])->first();
        $result['episode'] = $e === null ? null : cp_episode_snapshot($e);
    }
}
echo json_encode($result, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES | JSON_THROW_ON_ERROR), "\n";
