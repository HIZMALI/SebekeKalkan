import {defineConfig} from '@playwright/test';
import path from 'node:path';

const root=path.resolve('..');
const stamp=process.env.SE_TEST_RUN||'browser-current';
const evidence=process.env.SE_EVIDENCE_ROOT?path.resolve(root,process.env.SE_EVIDENCE_ROOT):path.join(root,'.calisma/playwright');
export default defineConfig({
  testDir:'./tests', timeout:120000, fullyParallel:false, workers:1, retries:0,
  outputDir:path.join(evidence,stamp,'artifacts'),
  reporter:[['list'],['json',{outputFile:path.join(evidence,stamp,'results.json')}],['junit',{outputFile:path.join(evidence,stamp,'junit.xml')}]],
  use:{baseURL:process.env.SE_BASE_URL||'http://127.0.0.1:18760',actionTimeout:12000,navigationTimeout:15000,locale:'tr-TR',timezoneId:'Europe/Istanbul',trace:process.env.MASTER_TRACE?'on':'retain-on-failure',screenshot:'only-on-failure',video:'off',acceptDownloads:true},
  projects:[
    {name:'edge-desktop',use:{channel:'msedge',viewport:{width:1366,height:900}}},
    {name:'chromium-mobile',use:{channel:'chrome',viewport:{width:390,height:844},isMobile:true,hasTouch:true,deviceScaleFactor:1}},
  ],
});
