export async function selectDocumentFont(budget=80){
  if(document.documentElement.dataset.uiFont)return
  let timer:ReturnType<typeof setTimeout>|undefined
  const available=document.fonts?.load('14px MiSansUI').then(faces=>faces.length>0).catch(()=>false)??Promise.resolve(false)
  const ready=await Promise.race([available,new Promise<boolean>(resolve=>{timer=setTimeout(()=>resolve(false),budget)})])
  clearTimeout(timer)
  if(!document.documentElement.dataset.uiFont)document.documentElement.dataset.uiFont=ready?'misans':'system'
}
