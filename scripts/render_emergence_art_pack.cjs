// Render the actual editable SVG masters to transparent PNG counterparts.
const fs = require('fs');
const path = require('path');
const sharp = require('C:/Users/admin/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/sharp');
const root = path.resolve(__dirname, '../assets/image/emergence_art_pack');
const manifest = JSON.parse(fs.readFileSync(path.join(root, 'manifest.json'), 'utf8'));
(async () => {
  for (const item of manifest.assets.filter(a => a.svg)) {
    await sharp(path.join(root,item.svg)).png().toFile(path.join(root,item.png));
  }
  console.log(JSON.stringify({rendered:manifest.assets.filter(a=>a.svg).length}));
})().catch(error => {console.error(error);process.exit(1)});
