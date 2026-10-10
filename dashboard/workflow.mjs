import { chromium } from '@playwright/test';
import { writeFile } from 'node:fs/promises';
const url=process.env.PITSTOP_URL||'http://127.0.0.1:7005';
if(!/^http:\/\/127\.0\.0\.1:70\d\d$/.test(url))throw new Error('Only a local sandbox is allowed.');
const output=process.argv[2];
const id=Date.now().toString().slice(-6),name=`Team28 Demo ${id}`,license=`HAC-${id.slice(0,3)}-${id.slice(3)}`;
const browser=await chromium.launch({channel:'msedge',headless:true});
const page=await browser.newPage();
page.setDefaultTimeout(30000);
const steps=[];
const result={StartedUtc:new Date().toISOString(),Url:url,Customer:name,License:license,Passed:false,Steps:steps};
try{
  await page.goto(url+'/CustomerManagement/New');
  for(const [field,value]of Object.entries({Name:name,Address:'Local sandbox',PostalCode:'110001',City:'Delhi',TelephoneNumber:'9999999999',EmailAddress:'team28@example.test'}))await page.locator(`[name="Customer.${field}"]`).fill(value);
  await page.locator('#SubmitButton').click();
  await page.getByText(name,{exact:true}).first().waitFor();steps.push('Customer registered');
  await page.goto(url+'/VehicleManagement/New');
  for(const [field,value]of Object.entries({LicenseNumber:license,Brand:'Bosch Demo',Type:'Sandbox'}))await page.locator(`[name="Vehicle.${field}"]`).fill(value);
  await page.locator('#SelectedCustomerId').selectOption({label:name});
  await page.locator('#SubmitButton').click();
  await page.getByText(license,{exact:true}).first().waitFor();steps.push('Vehicle registered');
  await page.goto(url+'/WorkshopManagement');
  await page.locator('a[href*="/WorkshopManagement/New"]').click();
  await page.locator('#StartTime').fill('08:00');await page.locator('#EndTime').fill('10:00');
  const description=`Day2 maintenance ${id}`;
  await page.locator('#Description').fill(description);
  const vehicle=page.locator('#SelectedVehicleLicenseNumber');
  await vehicle.selectOption(license);
  await page.locator('#SubmitButton').click();
  await page.getByText(description,{exact:true}).first().click();steps.push('Maintenance planned');
  await page.getByText('Planned',{exact:true}).waitFor();
  await page.locator('a[href*="/WorkshopManagement/Finish"]').click();
  await page.locator('#ActualStartTime').fill('08:00');await page.locator('#ActualEndTime').fill('09:30');
  await page.locator('#Notes').fill('Verified local hackathon workflow');
  await page.locator('#CompleteButton').click();
  await page.getByText('Completed',{exact:true}).waitFor();steps.push('Job completed');
  result.Passed=true;
}catch(error){result.Error=error.message;throw error;}
finally{result.FinishedUtc=new Date().toISOString();if(output)await writeFile(output,JSON.stringify(result,null,2));await browser.close();}
