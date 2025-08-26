<?php
require_once '../vendor/autoload.php';

use App\Access;
use Slim\Factory\AppFactory;
use Psr\Http\Message\ResponseInterface as Response;
use Psr\Http\Message\ServerRequestInterface as Request;

// Initialize database

$app = AppFactory::create();
$scriptName = $_SERVER['SCRIPT_NAME']; // Devuelve algo como "/midashboard/index.php"
$basePath = str_replace('/index.php', '', $scriptName); // "/midashboard"
$app->setBasePath($basePath);
$app->addBodyParsingMiddleware();
$app->addErrorMiddleware(true, true, true);
new Access($app);
// CORS middleware
$app->add(function (Request $request, $handler) {
    $response = $handler->handle($request);
    return $response
        ->withHeader('Access-Control-Allow-Origin', '*')
        ->withHeader('Access-Control-Allow-Headers', 'X-Requested-With, Content-Type, Accept, Origin, Authorization')
        ->withHeader('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, PATCH, OPTIONS');
});

// Serve static files
$app->get('/', function (Request $request, Response $response) {
    $html = file_get_contents(__DIR__ . '/../templates/dashboard.html');
    $response->getBody()->write($html);
    return $response->withHeader('Content-Type', 'text/html');
});

// API Routes for observability
$app->get('/ping', function (Request $request, Response $response, $args) use ($appManager) {
});

$app->run();
?>
