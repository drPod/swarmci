// Language bridge only: all integration behavior belongs to the official Nango SDK/templates.
import { Nango } from '@nangohq/node';
let input = '';
for await (const chunk of process.stdin) input += chunk;
const { operation, args = {} } = JSON.parse(input);
const nango = new Nango({ secretKey: process.env.NANGO_SECRET_KEY });
try {
  let result;
  switch (operation) {
    case 'connections': result = await nango.listConnections(args); break;
    case 'integrations': result = { data: (await nango.listIntegrations()).configs }; break;
    case 'providers': result = await nango.listProviders({}); break;
    case 'templates': result = await nango.getProviderTemplates(args); break;
    case 'functions': result = await nango.listFunctions({ uniqueKey: args.integration }); break;
    case 'deployment': {
      // This new endpoint has no SDK method yet; use Nango's documented template deployment API.
      const response = await fetch('https://api.nango.dev/functions/deployments', {
        method: 'POST', headers: { Authorization: `Bearer ${process.env.NANGO_SECRET_KEY}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ type: 'template', integration_id: args.integration, template: args.name, function_type: 'action' })
      });
      if (!response.ok) throw { response: { status: response.status } };
      result = await response.json(); break;
    }
    case 'connect': result = await nango.createConnectSession(args); break;
    case 'action': result = await nango.triggerAction(args.integration, args.connection, args.name, args.input); break;
    case 'proxy': result = (await nango.proxy(args)).data; break;
    default: throw Error('Unsupported SDK operation');
  }
  process.stdout.write(JSON.stringify(result));
} catch (error) {
  process.stderr.write(JSON.stringify({ operation, status: error.response?.status ?? null, error: 'Nango operation failed; inspect its execution logs and account scopes.' }));
  process.exitCode = 1;
}
