#!/usr/bin/env php
<?php
// Create/draft/publish through the installed Castopod models. This cohort targets
// the inspected 1.15.x interfaces; revalidate model compatibility after upgrades.
declare(strict_types=1);

require __DIR__ . '/castopod-bootstrap.php';

$o = getopt('', ['app:', 'podcast:', 'title:', 'slug:', 'audio:', 'description-file:', 'user:', 'cover:', 'season:', 'number:', 'message:', 'publish']);
cp_boot(cp_opt($o, 'app', null, true));

use App\Entities\Episode;
use App\Entities\Post;
use App\Models\EpisodeModel;
use App\Models\PodcastModel;
use App\Models\PostModel;
use CodeIgniter\Files\File;
use CodeIgniter\I18n\Time;
use Modules\Auth\Models\UserModel;

$operationLock = cp_episode_lock(cp_opt($o, 'app', null, true), cp_opt($o, 'podcast', null, true), cp_opt($o, 'slug', null, true));

$podcast = (new PodcastModel())->getPodcastByHandle(cp_opt($o, 'podcast', null, true));
if ($podcast === null) { fwrite(STDERR, "Podcast not found\n"); exit(1); }
$user = (new UserModel())->where('username', cp_opt($o, 'user', null, true))->first();
if (! $user) { fwrite(STDERR, "User not found\n"); exit(1); }
$audio = cp_opt($o, 'audio', null, true);
if (! is_file($audio) || ! in_array(strtolower(pathinfo($audio, PATHINFO_EXTENSION)), ['mp3', 'm4a'], true)) {
    fwrite(STDERR, "Audio must be an existing mp3 or m4a: {$audio}\n"); exit(1);
}
$slug = cp_opt($o, 'slug', null, true);
if (strlen($slug) > 128 || ! preg_match('/^[a-z0-9-]+$/', $slug)) { fwrite(STDERR, "Bad slug\n"); exit(1); }
$cover = cp_opt($o, 'cover');

$episodeModel = new EpisodeModel();
if ($episodeModel->where(['slug' => $slug, 'podcast_id' => $podcast->id])->first() instanceof Episode) {
    fwrite(STDERR, "An episode with slug '{$slug}' already exists in this podcast\n"); exit(1);
}

$db = db_connect();
$db->transStart();

$episode = new Episode([
    'created_by'           => $user->id,
    'updated_by'           => $user->id,
    'podcast_id'           => $podcast->id,
    'title'                => cp_opt($o, 'title', null, true),
    'slug'                 => $slug,
    'guid'                 => null,
    'audio'                => new File($audio),
    'cover'                => $cover ? new File($cover) : null,
    'description_markdown' => file_get_contents(cp_opt($o, 'description-file', null, true)),
    'location'             => null,
    'parental_advisory'    => null,
    'number'               => isset($o['number']) ? (int) $o['number'] : null,
    'season_number'        => isset($o['season']) ? (int) $o['season'] : null,
    'type'                 => 'full',
    'is_blocked'           => false,
    'custom_rss_string'    => null,
    'is_premium'           => false,
    'published_at'         => null,
]);

$id = (int) $episodeModel->insert($episode, true);
if ($id === 0) {
    $db->transRollback();
    fwrite(STDERR, "Insert failed: " . json_encode($episodeModel->errors()) . "\n"); exit(1);
}

if (isset($o['publish'])) {
    $episode = $episodeModel->getEpisodeById($id);
    $post = new Post([
        'actor_id'   => $podcast->actor_id,
        'episode_id' => $episode->id,
        'message'    => cp_opt($o, 'message', ''),
        'created_by' => $user->id,
    ]);
    if ($podcast->publication_status === 'scheduled') {
        $episode->published_at = $podcast->published_at->addSeconds(1);
    } else {
        $episode->published_at = Time::now();
    }
    $post->published_at = $episode->published_at;
    if (! (new PostModel())->addPost($post)) {
        $db->transRollback();
        fwrite(STDERR, "Post failed\n"); exit(1);
    }
    if (! $episodeModel->update($episode->id, $episode)) {
        $db->transRollback();
        fwrite(STDERR, "Publish failed: " . json_encode($episodeModel->errors()) . "\n"); exit(1);
    }
}
$db->transComplete();
if ($db->transStatus() === false) { fwrite(STDERR, "Transaction failed\n"); exit(1); }

$e = $episodeModel->getEpisodeById($id);
echo json_encode(['id' => $e->id, 'slug' => $e->slug, 'title' => $e->title, 'published_at' => (string) $e->published_at,
    'link' => $e->link, 'audio_url' => $e->audio_url], JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES), "\n";
