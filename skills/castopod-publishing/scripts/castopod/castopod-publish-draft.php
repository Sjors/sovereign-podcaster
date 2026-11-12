#!/usr/bin/env php
<?php
// Publish an existing draft once, using Castopod's normal post/model path.
declare(strict_types=1);
require __DIR__ . '/castopod-bootstrap.php';
$o = getopt('', ['app:', 'podcast:', 'slug:', 'user:', 'message:']);
cp_boot(cp_opt($o, 'app', null, true));

use App\Entities\Post;
use App\Models\EpisodeModel;
use App\Models\PodcastModel;
use App\Models\PostModel;
use CodeIgniter\I18n\Time;
use Modules\Auth\Models\UserModel;

$operationLock = cp_episode_lock(cp_opt($o, 'app', null, true), cp_opt($o, 'podcast', null, true), cp_opt($o, 'slug', null, true));

$podcast = (new PodcastModel())->getPodcastByHandle(cp_opt($o, 'podcast', null, true));
if ($podcast === null) { fwrite(STDERR, "Podcast not found\n"); exit(1); }
$user = (new UserModel())->where('username', cp_opt($o, 'user', null, true))->first();
if ($user === null) { fwrite(STDERR, "User not found\n"); exit(1); }
$model = new EpisodeModel();
$e = $model->where(['podcast_id' => $podcast->id, 'slug' => cp_opt($o, 'slug', null, true)])->first();
if ($e === null) { fwrite(STDERR, "Episode not found\n"); exit(1); }
if ($e->publication_status !== 'not_published') { fwrite(STDERR, "Episode is not a draft; inspect instead of republishing\n"); exit(1); }
if ($podcast->publication_status !== 'published') { fwrite(STDERR, "Podcast must already be published\n"); exit(1); }

$db = db_connect();
$db->transStart();
$e->published_at = Time::now();
$e->updated_by = $user->id;
$post = new Post(['actor_id' => $podcast->actor_id, 'episode_id' => $e->id,
    'message' => cp_opt($o, 'message', ''), 'created_by' => $user->id]);
$post->published_at = $e->published_at;
if (! (new PostModel())->addPost($post) || ! $model->update($e->id, $e)) {
    $db->transRollback(); fwrite(STDERR, "Publish failed\n"); exit(1);
}
$db->transComplete();
if ($db->transStatus() === false) { fwrite(STDERR, "Transaction failed\n"); exit(1); }
echo json_encode(['id' => (int) $e->id, 'slug' => $e->slug, 'link' => $e->link,
    'audio_url' => $e->audio_url], JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES), "\n";
