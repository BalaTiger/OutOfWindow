// NOAA fractional-year approximation. World north is -Z; east is +X.
// https://gml.noaa.gov/grad/solcalc/solareqns.PDF
const rad = Math.PI / 180;
export function localCalendar(date, timezone) {
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: timezone, year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23',
  }).formatToParts(date);
  const get = type => Number(parts.find(p => p.type === type).value);
  const result = Object.fromEntries(['year','month','day','hour','minute','second'].map(type => [type,get(type)]));
  result.offset = (Date.UTC(result.year,result.month-1,result.day,result.hour,result.minute,result.second) - Math.floor(date.getTime()/1000)*1000) / 3600000;
  return result;
}

export function solarPosition(location, hour, date = new Date()) {
  const local = localCalendar(date, location.timezone);
  const yearStart = Date.UTC(local.year,0,1), nextYear = Date.UTC(local.year+1,0,1);
  const days = (nextYear-yearStart)/86400000;
  const day = (Date.UTC(local.year,local.month-1,local.day)-yearStart)/86400000+1;
  const gamma = 2*Math.PI/days*(day-1+(hour-12)/24);
  const decl = .006918-.399912*Math.cos(gamma)+.070257*Math.sin(gamma)-.006758*Math.cos(2*gamma)+.000907*Math.sin(2*gamma)-.002697*Math.cos(3*gamma)+.00148*Math.sin(3*gamma);
  const eq = 229.18*(.000075+.001868*Math.cos(gamma)-.032077*Math.sin(gamma)-.014615*Math.cos(2*gamma)-.040849*Math.sin(2*gamma));
  const solarMinutes = hour*60+eq+4*location.longitude-60*local.offset;
  const ha = (solarMinutes/4-180)*rad, lat=location.latitude*rad;
  const elevation = Math.asin(Math.max(-1,Math.min(1,Math.sin(lat)*Math.sin(decl)+Math.cos(lat)*Math.cos(decl)*Math.cos(ha))));
  const azimuth = (Math.atan2(Math.sin(ha),Math.cos(ha)*Math.sin(lat)-Math.tan(decl)*Math.cos(lat))+Math.PI+2*Math.PI)%(2*Math.PI);
  return { elevation, azimuth, solarMinutes, localDate: `${local.year}-${local.month}-${local.day}` };
}

export function periodName(hour, solar) {
  const elevation = solar.elevation/rad;
  const morning = solar.solarMinutes < 720;
  if (elevation < -6) return hour < 5 ? '深夜' : '夜晚';
  if (elevation < 6) return morning ? '晨曦' : '暮色';
  if (elevation < 12) return morning ? '清晨' : '黄昏';
  if (hour < 11) return '上午';
  if (hour < 14) return '日中';
  return '午后';
}
