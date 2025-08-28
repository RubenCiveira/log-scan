<?php

require_once '../vendor/autoload.php';

use App\Access;
use App\ConfigManager;
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
    $manager = new ConfigManager();

    $python = realpath( '../') . '/pyenv/bin/python3';
    $script = 'agents.test';

    $descriptor = [
        0 => ['pipe', 'r'],
        1 => ['pipe', 'w'],
        2 => ['pipe', 'w'],
    ];
    $env = [
      'OPENAI_API_KEY' => $manager->get('OPENAI_API_KEY'),
    ];

    $process = proc_open(
        [$python, "-m", $script, '¿Quién es Rosalía? Busca y dame 3 datos.'],
        $descriptor,
        $pipes,
        realpath( '../') . '/agents',
        $env
    );

    $body = '';
    if (is_resource($process)) {
        $output = stream_get_contents($pipes[1]);
        $error = stream_get_contents($pipes[2]);
        if( $error ) {
            $body = '<h1>Error ejecutando el agente.</h1>' . $error;
        } else {
            fclose($pipes[1]);
            fclose($pipes[2]);
            proc_close($process);
            $data = json_decode( $output, true);
            $body = '<pre>'. print_r( $data, true ) . '</pre>';
        }
    } else {
        $body = '<h1>Imposible ejecutar el agente.</h1>';
    }
    $response->getBody()->write($body);
    return $response->withHeader('Content-Type', 'text/html');
});

// API Routes for observability
$app->get('/ping', function (Request $request, Response $response, $args) {
});

$app->run();
