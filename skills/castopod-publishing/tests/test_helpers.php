<?php
// Isolated lock regression; does not boot Castopod or use its database/media.
declare(strict_types=1);
require __DIR__ . '/../scripts/castopod/castopod-bootstrap.php';
if (!extension_loaded('posix')) { throw new RuntimeException('PHP POSIX extension required'); }
$base=sys_get_temp_dir().'/sovereign-podcaster-lock-test-'.bin2hex(random_bytes(8));
mkdir($base,0700);mkdir($base.'/writable',0700);
try {
    $first=cp_episode_lock($base,'fixture-show','fixture-episode');
    $blocked=false;
    try { $second=cp_episode_lock($base,'fixture-show','fixture-episode'); }
    catch (RuntimeException $e) { $blocked=true; }
    if (!$blocked) { throw new RuntimeException('Same-episode contention was not refused'); }
    $other=cp_episode_lock($base,'fixture-show','other-episode');fclose($other);
    fclose($first);
    $again=cp_episode_lock($base,'fixture-show','fixture-episode');fclose($again);
    echo "PHP episode locks: contention, independent target and release passed\n";
} finally {
    foreach (glob($base.'/writable/sovereign-podcaster-locks/*.lock') ?: [] as $path) { unlink($path); }
    rmdir($base.'/writable/sovereign-podcaster-locks');rmdir($base.'/writable');rmdir($base);
}
