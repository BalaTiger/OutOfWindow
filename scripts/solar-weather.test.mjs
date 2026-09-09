import test from 'node:test';
import assert from 'node:assert/strict';
import {solarPosition,localCalendar,periodName} from '../src/solar-time.js';
import {RainResponse} from '../src/rain-response.js';
const singapore={latitude:1.29,longitude:103.85,timezone:'Asia/Singapore'};
test('Singapore 10:47 is morning daylight, with an eastern sun near 56 degrees',()=>{
 const sun=solarPosition(singapore,10+47/60,new Date('2026-09-09T02:47:00Z'));
 assert.ok(sun.elevation*180/Math.PI>55 && sun.elevation*180/Math.PI<57);
 assert.ok(sun.azimuth*180/Math.PI>70 && sun.azimuth*180/Math.PI<90);
 assert.equal(periodName(10+47/60,sun),'上午');
});
test('Calendar day is local across UTC midnight, including leap day',()=>{
 const date=new Date('2024-02-28T16:30:00.999Z');
 assert.deepEqual(localCalendar(date,'Asia/Singapore'),{year:2024,month:2,day:29,hour:0,minute:30,second:0,offset:8});
 assert.equal(solarPosition(singapore,.5,date).localDate,'2024-2-29');
 assert.ok(solarPosition(singapore,.5,date).elevation<0);
});
test('DST offsets follow the requested date and place',()=>{
 assert.equal(localCalendar(new Date('2026-07-01T16:00:00Z'),'America/New_York').offset,-4);
 assert.equal(localCalendar(new Date('2026-01-01T16:00:00Z'),'America/New_York').offset,-5);
});
test('Twilight follows solar elevation, not a fixed wall-clock interval',()=>{
 assert.equal(periodName(10,{elevation:-.2,solarMinutes:500}),'夜晚');
 assert.equal(periodName(7,{elevation:.05,solarMinutes:400}),'晨曦');
 assert.equal(periodName(21,{elevation:.03,solarMinutes:1100}),'暮色');
});
test('Wetness accumulates, persists after rain, and eventually dries',()=>{
 const rain=new RainResponse();rain.setWeather('rain',{precipitation:2.5,windSpeed:10,windDirection:90});
 rain.update(1,1);const initial=rain.uniforms.rwWet.value;
 assert.ok(initial>0&&initial<.5);
 rain.update(30,31);assert.ok(rain.uniforms.rwWet.value>.95);assert.ok(rain.uniforms.rwWater.value>.65);
 const water=rain.uniforms.rwWater.value;rain.setWeather('clear');rain.update(1,32);
 assert.ok(rain.uniforms.rwWater.value>water*.9);assert.ok(rain.uniforms.rwWet.value>.9);
 rain.update(900,932);assert.ok(rain.uniforms.rwWet.value<.001);assert.ok(rain.uniforms.rwWater.value<.001);
});
test('Wind direction uses meteorological FROM bearing and km/h to m/s',()=>{
 const rain=new RainResponse();rain.setWeather('rain',{windSpeed:36,windGustSpeed:36,windDirection:90});rain.update(20,20);
 assert.ok(Math.abs(rain.uniforms.rwWind.value.x+10)<.001);assert.ok(Math.abs(rain.uniforms.rwWind.value.y)<.001);
 rain.setWeather('clear',{windSpeed:0,windGustSpeed:0});rain.update(20,40);assert.ok(rain.uniforms.rwWind.value.length()<.001);
});
