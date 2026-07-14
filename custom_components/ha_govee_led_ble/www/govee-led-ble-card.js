var x=globalThis,pr=x.ShadowRoot&&(x.ShadyCSS===void 0||x.ShadyCSS.nativeShadow)&&"adoptedStyleSheets"in Document.prototype&&"replace"in CSSStyleSheet.prototype,Er=Symbol(),Xr=new WeakMap;class Jr{constructor(r,w,u){if(this._$cssResult$=!0,u!==Er)throw Error("CSSResult is not constructable. Use `unsafeCSS` or `css` instead.");this.cssText=r,this.t=w}get styleSheet(){let r=this.i,w=this.t;if(pr&&r===void 0){let u=w!==void 0&&w.length===1;u&&(r=Xr.get(w)),r===void 0&&((this.i=r=new CSSStyleSheet).replaceSync(this.cssText),u&&Xr.set(w,r))}return r}toString(){return this.cssText}}var Cw=(r)=>new Jr(typeof r=="string"?r:r+"",void 0,Er),e=(r,...w)=>{let u=r.length===1?r[0]:w.reduce((o,n,b)=>o+(($)=>{if($._$cssResult$===!0)return $.cssText;if(typeof $=="number")return $;throw Error("Value passed to 'css' function must be a 'css' function result: "+$+". Use 'unsafeCSS' to pass non-literal values, but take care to ensure page security.")})(n)+r[b+1],r[0]);return new Jr(u,r,Er)},Dw=(r,w)=>{if(pr)r.adoptedStyleSheets=w.map((u)=>u instanceof CSSStyleSheet?u:u.styleSheet);else for(let u of w){let o=document.createElement("style"),n=x.litNonce;n!==void 0&&o.setAttribute("nonce",n),o.textContent=u.cssText,r.appendChild(o)}},_r=pr?(r)=>r:(r)=>r instanceof CSSStyleSheet?((w)=>{let u="";for(let o of w.cssRules)u+=o.cssText;return Cw(u)})(r):r,{is:Ww,defineProperty:kw,getOwnPropertyDescriptor:gw,getOwnPropertyNames:Gw,getOwnPropertySymbols:Xw,getPrototypeOf:_w}=Object,t=globalThis,Lr=t.trustedTypes,Lw=Lr?Lr.emptyScript:"",Hw=t.reactiveElementPolyfillSupport,f=(r,w)=>r,mr={toAttribute(r,w){switch(w){case Boolean:r=r?Lw:null;break;case Object:case Array:r=r==null?r:JSON.stringify(r)}return r},fromAttribute(r,w){let u=r;switch(w){case Boolean:u=r!==null;break;case Number:u=r===null?null:Number(r);break;case Object:case Array:try{u=JSON.parse(r)}catch(o){u=null}}return u}},yr=(r,w)=>!Ww(r,w),Hr={attribute:!0,type:String,converter:mr,reflect:!1,useDefault:!1,hasChanged:yr};Symbol.metadata??=Symbol("metadata"),t.litPropertyMetadata??=new WeakMap;class _ extends HTMLElement{static addInitializer(r){this.o(),(this.l??=[]).push(r)}static get observedAttributes(){return this.finalize(),this.u&&[...this.u.keys()]}static createProperty(r,w=Hr){if(w.state&&(w.attribute=!1),this.o(),this.prototype.hasOwnProperty(r)&&((w=Object.create(w)).wrapped=!0),this.elementProperties.set(r,w),!w.noAccessor){let u=Symbol(),o=this.getPropertyDescriptor(r,u,w);o!==void 0&&kw(this.prototype,r,o)}}static getPropertyDescriptor(r,w,u){let{get:o,set:n}=gw(this.prototype,r)??{get(){return this[w]},set(b){this[w]=b}};return{get:o,set(b){let $=o?.call(this);n?.call(this,b),this.requestUpdate(r,$,u)},configurable:!0,enumerable:!0}}static getPropertyOptions(r){return this.elementProperties.get(r)??Hr}static o(){if(this.hasOwnProperty(f("elementProperties")))return;let r=_w(this);r.finalize(),r.l!==void 0&&(this.l=[...r.l]),this.elementProperties=new Map(r.elementProperties)}static finalize(){if(this.hasOwnProperty(f("finalized")))return;if(this.finalized=!0,this.o(),this.hasOwnProperty(f("properties"))){let w=this.properties,u=[...Gw(w),...Xw(w)];for(let o of u)this.createProperty(o,w[o])}let r=this[Symbol.metadata];if(r!==null){let w=litPropertyMetadata.get(r);if(w!==void 0)for(let[u,o]of w)this.elementProperties.set(u,o)}this.u=new Map;for(let[w,u]of this.elementProperties){let o=this.p(w,u);o!==void 0&&this.u.set(o,w)}this.elementStyles=this.finalizeStyles(this.styles)}static finalizeStyles(r){let w=[];if(Array.isArray(r)){let u=new Set(r.flat(1/0).reverse());for(let o of u)w.unshift(_r(o))}else r!==void 0&&w.push(_r(r));return w}static p(r,w){let u=w.attribute;return u===!1?void 0:typeof u=="string"?u:typeof r=="string"?r.toLowerCase():void 0}constructor(){super(),this.v=void 0,this.isUpdatePending=!1,this.hasUpdated=!1,this.m=null,this._()}_(){this.S=new Promise((r)=>this.enableUpdating=r),this._$AL=new Map,this.$(),this.requestUpdate(),this.constructor.l?.forEach((r)=>r(this))}addController(r){(this.P??=new Set).add(r),this.renderRoot!==void 0&&this.isConnected&&r.hostConnected?.()}removeController(r){this.P?.delete(r)}$(){let r=new Map,w=this.constructor.elementProperties;for(let u of w.keys())this.hasOwnProperty(u)&&(r.set(u,this[u]),delete this[u]);r.size>0&&(this.v=r)}createRenderRoot(){let r=this.shadowRoot??this.attachShadow(this.constructor.shadowRootOptions);return Dw(r,this.constructor.elementStyles),r}connectedCallback(){this.renderRoot??=this.createRenderRoot(),this.enableUpdating(!0),this.P?.forEach((r)=>r.hostConnected?.())}enableUpdating(r){}disconnectedCallback(){this.P?.forEach((r)=>r.hostDisconnected?.())}attributeChangedCallback(r,w,u){this._$AK(r,u)}C(r,w){let u=this.constructor.elementProperties.get(r),o=this.constructor.p(r,u);if(o!==void 0&&u.reflect===!0){let n=(u.converter?.toAttribute!==void 0?u.converter:mr).toAttribute(w,u.type);this.m=r,n==null?this.removeAttribute(o):this.setAttribute(o,n),this.m=null}}_$AK(r,w){let u=this.constructor,o=u.u.get(r);if(o!==void 0&&this.m!==o){let n=u.getPropertyOptions(o),b=typeof n.converter=="function"?{fromAttribute:n.converter}:n.converter?.fromAttribute!==void 0?n.converter:mr;this.m=o;let $=b.fromAttribute(w,n.type);this[o]=$??this.T?.get(o)??$,this.m=null}}requestUpdate(r,w,u,o=!1,n){if(r!==void 0){let b=this.constructor;if(o===!1&&(n=this[r]),u??=b.getPropertyOptions(r),!((u.hasChanged??yr)(n,w)||u.useDefault&&u.reflect&&n===this.T?.get(r)&&!this.hasAttribute(b.p(r,u))))return;this.M(r,w,u)}this.isUpdatePending===!1&&(this.S=this.k())}M(r,w,{useDefault:u,reflect:o,wrapped:n},b){u&&!(this.T??=new Map).has(r)&&(this.T.set(r,b??w??this[r]),n!==!0||b!==void 0)||(this._$AL.has(r)||(this.hasUpdated||u||(w=void 0),this._$AL.set(r,w)),o===!0&&this.m!==r&&(this.A??=new Set).add(r))}async k(){this.isUpdatePending=!0;try{await this.S}catch(w){Promise.reject(w)}let r=this.scheduleUpdate();return r!=null&&await r,!this.isUpdatePending}scheduleUpdate(){return this.performUpdate()}performUpdate(){if(!this.isUpdatePending)return;if(!this.hasUpdated){if(this.renderRoot??=this.createRenderRoot(),this.v){for(let[o,n]of this.v)this[o]=n;this.v=void 0}let u=this.constructor.elementProperties;if(u.size>0)for(let[o,n]of u){let{wrapped:b}=n,$=this[o];b!==!0||this._$AL.has(o)||$===void 0||this.M(o,void 0,n,$)}}let r=!1,w=this._$AL;try{r=this.shouldUpdate(w),r?(this.willUpdate(w),this.P?.forEach((u)=>u.hostUpdate?.()),this.update(w)):this.U()}catch(u){throw r=!1,this.U(),u}r&&this._$AE(w)}willUpdate(r){}_$AE(r){this.P?.forEach((w)=>w.hostUpdated?.()),this.hasUpdated||(this.hasUpdated=!0,this.firstUpdated(r)),this.updated(r)}U(){this._$AL=new Map,this.isUpdatePending=!1}get updateComplete(){return this.getUpdateComplete()}getUpdateComplete(){return this.S}shouldUpdate(r){return!0}update(r){this.A&&=this.A.forEach((w)=>this.C(w,this[w])),this.U()}updated(r){}firstUpdated(r){}}_.elementStyles=[],_.shadowRootOptions={mode:"open"},_[f("elementProperties")]=new Map,_[f("finalized")]=new Map,Hw?.({ReactiveElement:_}),(t.reactiveElementVersions??=[]).push("2.1.2");var qr=globalThis,Pr=(r)=>r,s=qr.trustedTypes,hr=s?s.createPolicy("lit-html",{createHTML:(r)=>r}):void 0,Ir="$lit$",W=`lit$${Math.random().toFixed(9).slice(2)}$`,Or="?"+W,Pw=`<${Or}>`,H=document,N=()=>H.createComment(""),S=(r)=>r===null||typeof r!="object"&&typeof r!="function",Br=Array.isArray,hw=(r)=>Br(r)||typeof r?.[Symbol.iterator]=="function",$r=`[ 	
\f\r]`,O=/<(?:(!--|\/[^a-zA-Z])|(\/?[a-zA-Z][^>\s]*)|(\/?$))/g,Kr=/-->/g,Mr=/>/g,X=RegExp(`>|${$r}(?:([^\\s"'>=/]+)(${$r}*=${$r}*(?:[^ 	
\f\r"'\`<>=]|("|')|))|$)`,"g"),lr=/'/g,Ar=/"/g,fr=/^(?:script|style|textarea|title)$/i,Fr=(r)=>(w,...u)=>({_$litType$:r,strings:w,values:u}),m=Fr(1),Tw=Fr(2),iw=Fr(3),K=Symbol.for("lit-noChange"),q=Symbol.for("lit-nothing"),Ur=new WeakMap,L=H.createTreeWalker(H,129);function Nr(r,w){if(!Br(r)||!r.hasOwnProperty("raw"))throw Error("invalid template strings array");return hr!==void 0?hr.createHTML(w):w}var Kw=(r,w)=>{let u=r.length-1,o=[],n,b=w===2?"<svg>":w===3?"<math>":"",$=O;for(let E=0;E<u;E++){let p=r[E],F,J,R=-1,z=0;for(;z<p.length&&($.lastIndex=z,J=$.exec(p),J!==null);)z=$.lastIndex,$===O?J[1]==="!--"?$=Kr:J[1]!==void 0?$=Mr:J[2]!==void 0?(fr.test(J[2])&&(n=RegExp("</"+J[2],"g")),$=X):J[3]!==void 0&&($=X):$===X?J[0]===">"?($=n??O,R=-1):J[1]===void 0?R=-2:(R=$.lastIndex-J[2].length,F=J[1],$=J[3]===void 0?X:J[3]==='"'?Ar:lr):$===Ar||$===lr?$=X:$===Kr||$===Mr?$=O:($=X,n=void 0);let G=$===X&&r[E+1].startsWith("/>")?" ":"";b+=$===O?p+Pw:R>=0?(o.push(F),p.slice(0,R)+Ir+p.slice(R)+W+G):p+W+(R===-2?E:G)}return[Nr(r,b+(r[u]||"<?>")+(w===2?"</svg>":w===3?"</math>":"")),o]};class v{constructor({strings:r,_$litType$:w},u){let o;this.parts=[];let n=0,b=0,$=r.length-1,E=this.parts,[p,F]=Kw(r,w);if(this.el=v.createElement(p,u),L.currentNode=this.el.content,w===2||w===3){let J=this.el.content.firstChild;J.replaceWith(...J.childNodes)}for(;(o=L.nextNode())!==null&&E.length<$;){if(o.nodeType===1){if(o.hasAttributes())for(let J of o.getAttributeNames())if(J.endsWith(Ir)){let R=F[b++],z=o.getAttribute(J).split(W),G=/([.?@])?(.*)/.exec(R);E.push({type:1,index:n,name:G[2],strings:z,ctor:G[1]==="."?vr:G[1]==="?"?dr:G[1]==="@"?Tr:T}),o.removeAttribute(J)}else J.startsWith(W)&&(E.push({type:6,index:n}),o.removeAttribute(J));if(fr.test(o.tagName)){let J=o.textContent.split(W),R=J.length-1;if(R>0){o.textContent=s?s.emptyScript:"";for(let z=0;z<R;z++)o.append(J[z],N()),L.nextNode(),E.push({type:2,index:++n});o.append(J[R],N())}}}else if(o.nodeType===8)if(o.data===Or)E.push({type:2,index:n});else{let J=-1;for(;(J=o.data.indexOf(W,J+1))!==-1;)E.push({type:7,index:n}),J+=W.length-1}n++}}static createElement(r,w){let u=H.createElement("template");return u.innerHTML=r,u}}function M(r,w,u=r,o){if(w===K)return w;let n=o!==void 0?u.N?.[o]:u.O,b=S(w)?void 0:w._$litDirective$;return n?.constructor!==b&&(n?._$AO?.(!1),b===void 0?n=void 0:(n=new b(r),n._$AT(r,u,o)),o!==void 0?(u.N??=[])[o]=n:u.O=n),n!==void 0&&(w=M(r,n._$AS(r,w.values),n,o)),w}class Sr{constructor(r,w){this._$AV=[],this._$AN=void 0,this._$AD=r,this._$AM=w}get parentNode(){return this._$AM.parentNode}get _$AU(){return this._$AM._$AU}R(r){let{el:{content:w},parts:u}=this._$AD,o=(r?.creationScope??H).importNode(w,!0);L.currentNode=o;let n=L.nextNode(),b=0,$=0,E=u[0];for(;E!==void 0;){if(b===E.index){let p;E.type===2?p=new d(n,n.nextSibling,this,r):E.type===1?p=new E.ctor(n,E.name,E.strings,this,r):E.type===6&&(p=new ir(n,this,r)),this._$AV.push(p),E=u[++$]}b!==E?.index&&(n=L.nextNode(),b++)}return L.currentNode=H,o}V(r){let w=0;for(let u of this._$AV)u!==void 0&&(u.strings!==void 0?(u._$AI(r,u,w),w+=u.strings.length-2):u._$AI(r[w])),w++}}class d{get _$AU(){return this._$AM?._$AU??this.D}constructor(r,w,u,o){this.type=2,this._$AH=q,this._$AN=void 0,this._$AA=r,this._$AB=w,this._$AM=u,this.options=o,this.D=o?.isConnected??!0}get parentNode(){let r=this._$AA.parentNode,w=this._$AM;return w!==void 0&&r?.nodeType===11&&(r=w.parentNode),r}get startNode(){return this._$AA}get endNode(){return this._$AB}_$AI(r,w=this){r=M(this,r,w),S(r)?r===q||r==null||r===""?(this._$AH!==q&&this._$AR(),this._$AH=q):r!==this._$AH&&r!==K&&this.L(r):r._$litType$!==void 0?this.j(r):r.nodeType!==void 0?this.I(r):hw(r)?this.H(r):this.L(r)}B(r){return this._$AA.parentNode.insertBefore(r,this._$AB)}I(r){this._$AH!==r&&(this._$AR(),this._$AH=this.B(r))}L(r){this._$AH!==q&&S(this._$AH)?this._$AA.nextSibling.data=r:this.I(H.createTextNode(r)),this._$AH=r}j(r){let{values:w,_$litType$:u}=r,o=typeof u=="number"?this._$AC(r):(u.el===void 0&&(u.el=v.createElement(Nr(u.h,u.h[0]),this.options)),u);if(this._$AH?._$AD===o)this._$AH.V(w);else{let n=new Sr(o,this),b=n.R(this.options);n.V(w),this.I(b),this._$AH=n}}_$AC(r){let w=Ur.get(r.strings);return w===void 0&&Ur.set(r.strings,w=new v(r)),w}H(r){Br(this._$AH)||(this._$AH=[],this._$AR());let w=this._$AH,u,o=0;for(let n of r)o===w.length?w.push(u=new d(this.B(N()),this.B(N()),this,this.options)):u=w[o],u._$AI(n),o++;o<w.length&&(this._$AR(u&&u._$AB.nextSibling,o),w.length=o)}_$AR(r=this._$AA.nextSibling,w){for(this._$AP?.(!1,!0,w);r!==this._$AB;){let u=Pr(r).nextSibling;Pr(r).remove(),r=u}}setConnected(r){this._$AM===void 0&&(this.D=r,this._$AP?.(r))}}class T{get tagName(){return this.element.tagName}get _$AU(){return this._$AM._$AU}constructor(r,w,u,o,n){this.type=1,this._$AH=q,this._$AN=void 0,this.element=r,this.name=w,this._$AM=o,this.options=n,u.length>2||u[0]!==""||u[1]!==""?(this._$AH=Array(u.length-1).fill(new String),this.strings=u):this._$AH=q}_$AI(r,w=this,u,o){let n=this.strings,b=!1;if(n===void 0)r=M(this,r,w,0),b=!S(r)||r!==this._$AH&&r!==K,b&&(this._$AH=r);else{let $=r,E,p;for(r=n[0],E=0;E<n.length-1;E++)p=M(this,$[u+E],w,E),p===K&&(p=this._$AH[E]),b||=!S(p)||p!==this._$AH[E],p===q?r=q:r!==q&&(r+=(p??"")+n[E+1]),this._$AH[E]=p}b&&!o&&this.W(r)}W(r){r===q?this.element.removeAttribute(this.name):this.element.setAttribute(this.name,r??"")}}class vr extends T{constructor(){super(...arguments),this.type=3}W(r){this.element[this.name]=r===q?void 0:r}}class dr extends T{constructor(){super(...arguments),this.type=4}W(r){this.element.toggleAttribute(this.name,!!r&&r!==q)}}class Tr extends T{constructor(r,w,u,o,n){super(r,w,u,o,n),this.type=5}_$AI(r,w=this){if((r=M(this,r,w,0)??q)===K)return;let u=this._$AH,o=r===q&&u!==q||r.capture!==u.capture||r.once!==u.once||r.passive!==u.passive,n=r!==q&&(u===q||o);o&&this.element.removeEventListener(this.name,this,u),n&&this.element.addEventListener(this.name,this,r),this._$AH=r}handleEvent(r){typeof this._$AH=="function"?this._$AH.call(this.options?.host??this.element,r):this._$AH.handleEvent(r)}}class ir{constructor(r,w,u){this.element=r,this.type=6,this._$AN=void 0,this._$AM=w,this.options=u}get _$AU(){return this._$AM._$AU}_$AI(r){M(this,r)}}var Mw=qr.litHtmlPolyfillSupport;Mw?.(v,d),(qr.litHtmlVersions??=[]).push("3.3.3");var lw=(r,w,u)=>{let o=u?.renderBefore??w,n=o._$litPart$;if(n===void 0){let b=u?.renderBefore??null;o._$litPart$=n=new d(w.insertBefore(N(),b),b,void 0,u??{})}return n._$AI(r),n},Rr=globalThis;class Z extends _{constructor(){super(...arguments),this.renderOptions={host:this},this.rt=void 0}createRenderRoot(){let r=super.createRenderRoot();return this.renderOptions.renderBefore??=r.firstChild,r}update(r){let w=this.render();this.hasUpdated||(this.renderOptions.isConnected=this.isConnected),super.update(r),this.rt=lw(w,this.renderRoot,this.renderOptions)}connectedCallback(){super.connectedCallback(),this.rt?.setConnected(!0)}disconnectedCallback(){super.disconnectedCallback(),this.rt?.setConnected(!1)}render(){return K}}Z._$litElement$=!0,Z.finalized=!0,Rr.litElementHydrateSupport?.({LitElement:Z});var Aw=Rr.litElementPolyfillSupport;Aw?.({LitElement:Z});(Rr.litElementVersions??=[]).push("4.2.2");var cr=e`
    ha-card {
      overflow: hidden;
    }
    .body {
      display: flex;
      flex-direction: column;
      gap: 20px;
      padding: 16px;
    }
    .notice {
      padding: 16px;
      color: var(--secondary-text-color);
    }
    section {
      display: flex;
      flex-direction: column;
      gap: 10px;
    }
    .row {
      display: flex;
      align-items: center;
      gap: 10px;
      flex-wrap: wrap;
    }
    .heading {
      justify-content: space-between;
    }
    .label {
      font-weight: 600;
      color: var(--primary-text-color);
    }
    .hint {
      color: var(--secondary-text-color);
      font-size: 0.85em;
    }
    /* Painter strip */
    .strip {
      display: grid;
      gap: 3px;
      padding: 4px;
      border-radius: var(--ha-card-border-radius, 12px);
      background: var(--divider-color);
      touch-action: pan-x pan-y;
      user-select: none;
      outline: none;
    }
    .strip:focus-visible {
      box-shadow: 0 0 0 2px var(--primary-color);
    }
    .cell {
      position: relative;
      aspect-ratio: 1 / 1.6;
      border-radius: 6px;
      background: var(--card-background-color);
      cursor: pointer;
      display: flex;
      align-items: flex-end;
      justify-content: center;
      transition: transform 0.05s ease;
    }
    .cell.off {
      background: var(--card-background-color);
      border: 1px dashed var(--secondary-text-color);
      opacity: 0.5;
    }
    .cell .cell-num {
      font-size: 9px;
      line-height: 1.2;
      font-weight: 600;
      padding: 1px 4px;
      margin-bottom: 2px;
      border-radius: 6px;
      background: rgba(0, 0, 0, 0.4);
      color: #fff;
      pointer-events: none;
    }
    .cell.off .cell-num,
    .cell.unchanged .cell-num {
      background: var(--card-background-color);
      color: var(--secondary-text-color);
    }
    .cell.sel {
      outline: 3px solid var(--primary-color);
      outline-offset: -1px;
      transform: translateY(-2px);
    }
    .cell.cursor::after {
      content: "";
      position: absolute;
      inset: -3px;
      border-radius: 8px;
      border: 2px dashed var(--primary-text-color);
      pointer-events: none;
    }
    /* Gradient */
    .gradient-bar {
      position: relative;
      height: 34px;
      border-radius: 17px;
      border: 1px solid var(--divider-color);
    }
    .handle {
      position: absolute;
      top: 50%;
      width: 28px;
      height: 28px;
      border-radius: 50%;
      transform: translate(-50%, -50%);
      border: 2px solid var(--card-background-color);
      box-shadow: 0 0 0 1px var(--divider-color);
      cursor: grab;
      touch-action: none;
    }
    .handle.dragging {
      cursor: grabbing;
      transform: translate(-50%, -50%) scale(1.25);
    }
    .stops {
      display: flex;
      align-items: center;
      gap: 8px;
      flex-wrap: wrap;
    }
    .stop {
      display: flex;
      align-items: center;
      gap: 4px;
      padding: 4px;
      border: 1px solid var(--divider-color);
      border-radius: 9px;
      background: var(--secondary-background-color);
    }
    /* Presets */
    .presets {
      gap: 8px;
    }
    .preset {
      display: inline-flex;
      flex-direction: column;
      gap: 4px;
      padding: 4px;
      border: 1px solid var(--divider-color);
      background: var(--card-background-color);
      color: var(--primary-text-color);
      border-radius: 10px;
      cursor: pointer;
      font: inherit;
    }
    .preset:hover {
      border-color: var(--primary-color);
    }
    .preset .swatch {
      width: 64px;
      height: 22px;
      border-radius: 6px;
      border: 1px solid var(--divider-color);
    }
    .preset .preset-name {
      font-size: 0.8em;
      text-align: center;
      color: var(--secondary-text-color);
    }
    /* Preview */
    canvas.preview {
      width: 100%;
      height: 44px;
      display: block;
      border-radius: 8px;
      background: var(--card-background-color);
    }
    /* Controls */
    .btn {
      border: 1px solid var(--divider-color);
      background: var(--card-background-color);
      color: var(--primary-text-color);
      border-radius: 18px;
      padding: 6px 14px;
      font: inherit;
      cursor: pointer;
    }
    .btn:hover {
      border-color: var(--primary-color);
    }
    .btn.primary {
      background: var(--primary-color);
      color: var(--text-primary-color, #fff);
      border-color: var(--primary-color);
    }
    .btn.tiny {
      border-radius: 50%;
      width: 26px;
      height: 26px;
      padding: 0;
      line-height: 1;
    }
    .btn[disabled] {
      opacity: 0.4;
      cursor: not-allowed;
    }
    .btn.primary[disabled] {
      opacity: 1;
      background: var(--disabled-color, var(--divider-color));
      color: var(--disabled-text-color, var(--secondary-text-color));
      border-color: var(--divider-color);
      cursor: not-allowed;
    }
    input[type="color"] {
      width: 42px;
      height: 30px;
      border: 1px solid var(--divider-color);
      border-radius: 6px;
      background: var(--card-background-color);
      padding: 2px;
      cursor: pointer;
    }
    input[type="text"] {
      border: 1px solid var(--divider-color);
      border-radius: 8px;
      background: var(--card-background-color);
      color: var(--primary-text-color);
      padding: 7px 10px;
      font: inherit;
    }
    input[type="text"]:focus-visible {
      outline: none;
      border-color: var(--primary-color);
      box-shadow: 0 0 0 1px var(--primary-color);
    }
    textarea {
      border: 1px solid var(--divider-color);
      border-radius: 8px;
      background: var(--card-background-color);
      color: var(--primary-text-color);
      padding: 10px;
      font: 0.85em/1.4 ui-monospace, SFMono-Regular, Consolas, monospace;
      resize: vertical;
    }
    textarea:focus-visible {
      outline: none;
      border-color: var(--primary-color);
      box-shadow: 0 0 0 1px var(--primary-color);
    }
    .effect-name {
      flex: 1 1 12ch;
      min-width: 12ch;
    }
    .edit-band {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
      padding: 8px 10px;
      border: 1px solid var(--primary-color);
      border-radius: 8px;
      color: var(--primary-text-color);
      background: var(--secondary-background-color);
      font-size: 0.85em;
    }
    .pending-author {
      padding: 12px;
      border: 1px dashed var(--divider-color);
      border-radius: 10px;
      background: var(--secondary-background-color);
    }
    .import-panel {
      border: 1px solid var(--divider-color);
      border-radius: 10px;
      overflow: hidden;
    }
    .import-panel summary {
      padding: 10px 12px;
      color: var(--primary-text-color);
      font-weight: 600;
      cursor: pointer;
    }
    .import-panel[open] summary {
      border-bottom: 1px solid var(--divider-color);
    }
    .import-body {
      display: flex;
      flex-direction: column;
      gap: 10px;
      padding: 12px;
    }
    .import-json {
      min-height: 130px;
    }
    .import-file {
      display: none;
    }
    /* Custom effects */
    .help {
      margin: 0;
      color: var(--secondary-text-color);
      font-size: 0.85em;
    }
    .feedback {
      border-radius: 8px;
      padding: 8px 10px;
      font-size: 0.9em;
      border: 1px solid var(--divider-color);
      background: var(--secondary-background-color);
      color: var(--primary-text-color);
    }
    .feedback.error {
      border-color: var(--error-color);
      color: var(--error-color);
    }
    .feedback.info {
      border-color: var(--success-color, var(--primary-color));
    }
    .draft-confirm {
      display: flex;
      flex-direction: column;
      gap: 8px;
      padding: 10px;
      border: 1px solid var(--warning-color, #f9a825);
      border-radius: 8px;
      background: var(--secondary-background-color);
      color: var(--primary-text-color);
      font-size: 0.9em;
    }
    .effects {
      list-style: none;
      margin: 0;
      padding: 0;
      display: flex;
      flex-direction: column;
      gap: 8px;
    }
    .effect {
      display: flex;
      align-items: center;
      gap: 8px;
      flex-wrap: wrap;
    }
    .effect-main {
      display: flex;
      align-items: center;
      gap: 8px;
      flex: 1 1 220px;
      min-width: 0;
    }
    .effect-actions {
      display: flex;
      align-items: center;
      justify-content: flex-end;
      gap: 6px;
      flex: 1 1 auto;
      flex-wrap: wrap;
    }
    .effect-more summary {
      list-style: none;
    }
    .effect-more summary::-webkit-details-marker {
      display: none;
    }
    .effect-more[open] {
      flex-basis: 100%;
    }
    .more-actions {
      display: flex;
      justify-content: flex-end;
      gap: 6px;
      margin-top: 6px;
      flex-wrap: wrap;
    }
    .effect-label {
      flex: 1 1 auto;
      min-width: 0;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      color: var(--primary-text-color);
    }
    /* Studio shell: header, status band, tabs */
    .card-head {
      display: flex;
      flex-direction: column;
      gap: 10px;
      padding: 16px 16px 0;
    }
    .title {
      font-size: 1.15em;
      font-weight: 600;
      color: var(--primary-text-color);
    }
    .status {
      display: flex;
      align-items: center;
      gap: 8px;
      color: var(--secondary-text-color);
      font-size: 0.9em;
      min-width: 0;
    }
    .status .current {
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      color: var(--primary-text-color);
    }
    .tabs {
      display: flex;
      gap: 4px;
      background: var(--divider-color);
      border-radius: 22px;
      padding: 4px;
    }
    .tab {
      flex: 1 1 0;
      border: none;
      background: transparent;
      color: var(--secondary-text-color);
      border-radius: 18px;
      padding: 8px 12px;
      font: inherit;
      font-weight: 600;
      cursor: pointer;
    }
    .tab:hover {
      color: var(--primary-text-color);
    }
    .tab.active {
      background: var(--card-background-color);
      color: var(--primary-text-color);
      box-shadow: 0 1px 3px rgba(0, 0, 0, 0.18);
    }
    .tab:focus-visible {
      outline: none;
      box-shadow: 0 0 0 2px var(--primary-color);
    }
    /* Studio: kind pill picker */
    .kinds {
      display: flex;
      gap: 6px;
      flex-wrap: wrap;
    }
    .kind {
      border: 1px solid var(--divider-color);
      background: var(--card-background-color);
      color: var(--primary-text-color);
      border-radius: 16px;
      padding: 6px 14px;
      font: inherit;
      cursor: pointer;
    }
    .kind:hover {
      border-color: var(--primary-color);
    }
    .kind.active {
      background: var(--primary-color);
      color: var(--text-primary-color, #fff);
      border-color: var(--primary-color);
    }
    .kind.soon,
    .kind:disabled {
      opacity: 1;
      border-style: dashed;
      background: var(--secondary-background-color);
      color: var(--secondary-text-color);
      cursor: default;
    }
    .kind.soon:hover,
    .kind:disabled:hover {
      border-color: var(--divider-color);
    }
    .kind .soon-tag {
      font-size: 0.7em;
      text-transform: uppercase;
      letter-spacing: 0.04em;
      background: var(--divider-color);
      color: var(--secondary-text-color);
      border-radius: 8px;
      padding: 1px 6px;
      margin-left: 6px;
    }
    .kind:focus-visible {
      outline: none;
      box-shadow: 0 0 0 2px var(--primary-color);
    }
    /* Studio: unchanged (leave-as-is) segment cells */
    .cell.unchanged {
      background:
        repeating-linear-gradient(
          45deg,
          transparent,
          transparent 5px,
          var(--divider-color) 5px,
          var(--divider-color) 6px
        ),
        var(--card-background-color);
      border: 1px solid var(--divider-color);
    }
    .cell.background {
      background:
        repeating-linear-gradient(
          45deg,
          transparent,
          transparent 5px,
          rgba(255, 255, 255, 0.24) 5px,
          rgba(255, 255, 255, 0.24) 6px
        ),
        var(--cell-background);
      border: 1px solid var(--divider-color);
    }
    .colour-control {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      color: var(--secondary-text-color);
      font-size: 0.85em;
    }
    .motion-grid {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 8px;
    }
    .motion {
      border: 1px solid var(--divider-color);
      background: var(--card-background-color);
      color: var(--primary-text-color);
      border-radius: 10px;
      padding: 9px 10px;
      font: inherit;
      cursor: pointer;
    }
    .motion:hover {
      border-color: var(--primary-color);
    }
    .motion.active {
      border-color: var(--primary-color);
      background: var(--primary-color);
      color: var(--text-primary-color, #fff);
    }
    .motion:focus-visible {
      outline: none;
      box-shadow: 0 0 0 2px var(--primary-color);
    }
    .range-row {
      display: grid;
      grid-template-columns: minmax(80px, auto) minmax(120px, 1fr) 4ch;
      align-items: center;
      gap: 10px;
      color: var(--primary-text-color);
    }
    .range-row input[type="range"] {
      width: 100%;
      accent-color: var(--primary-color);
    }
    .range-row output {
      text-align: right;
      color: var(--secondary-text-color);
      font-variant-numeric: tabular-nums;
    }
    .preview-badge {
      color: var(--secondary-text-color);
      font-size: 0.78em;
      border: 1px solid var(--divider-color);
      border-radius: 10px;
      padding: 2px 7px;
    }
    .family-grid,
    .variant-grid {
      display: flex;
      gap: 7px;
      flex-wrap: wrap;
    }
    .family,
    .variant {
      border: 1px solid var(--divider-color);
      background: var(--card-background-color);
      color: var(--primary-text-color);
      border-radius: 16px;
      padding: 7px 12px;
      font: inherit;
      cursor: pointer;
    }
    .family:hover,
    .variant:hover {
      border-color: var(--primary-color);
    }
    .family.active,
    .variant.active {
      border-color: var(--primary-color);
      background: var(--primary-color);
      color: var(--text-primary-color, #fff);
    }
    .family:focus-visible,
    .variant:focus-visible {
      outline: none;
      box-shadow: 0 0 0 2px var(--primary-color);
    }
    .palette-editor {
      display: flex;
      align-items: stretch;
      gap: 8px;
      flex-wrap: wrap;
    }
    .palette-chip {
      display: grid;
      grid-template-columns: auto auto auto;
      align-items: center;
      gap: 4px;
      padding: 5px;
      border: 1px solid var(--divider-color);
      border-radius: 10px;
      background: var(--secondary-background-color);
    }
    .palette-chip input[type="color"] {
      grid-column: 1 / -1;
      width: 100%;
    }
    .palette-number {
      color: var(--secondary-text-color);
      font-size: 0.8em;
      font-variant-numeric: tabular-nums;
    }
    .palette-chip .btn.danger {
      border-color: var(--error-color);
      color: var(--error-color);
    }
    .palette-add {
      min-height: 76px;
      border-style: dashed;
    }
    .combo-chain {
      list-style: none;
      margin: 0;
      padding: 0;
      display: flex;
      flex-direction: column;
      gap: 8px;
    }
    .combo-step {
      display: grid;
      grid-template-columns: auto minmax(100px, 1fr) minmax(120px, 1fr);
      align-items: center;
      gap: 8px;
      padding: 8px;
      border: 1px solid var(--divider-color);
      border-radius: 10px;
      background: var(--secondary-background-color);
    }
    .combo-number {
      color: var(--secondary-text-color);
      font-variant-numeric: tabular-nums;
      font-weight: 600;
    }
    .combo-step select {
      width: 100%;
      border: 1px solid var(--divider-color);
      border-radius: 8px;
      background: var(--card-background-color);
      color: var(--primary-text-color);
      padding: 7px 9px;
      font: inherit;
    }
    .combo-step select:focus-visible {
      outline: none;
      border-color: var(--primary-color);
      box-shadow: 0 0 0 1px var(--primary-color);
    }
    .combo-actions {
      display: flex;
      gap: 4px;
      grid-column: 2 / -1;
      justify-content: flex-end;
    }
    .combo-actions .btn.danger {
      border-color: var(--error-color);
      color: var(--error-color);
    }
    .sr-only {
      position: absolute;
      width: 1px;
      height: 1px;
      padding: 0;
      margin: -1px;
      overflow: hidden;
      clip: rect(0, 0, 0, 0);
      white-space: nowrap;
      border: 0;
    }
    /* Studio: "coming next" caption row of disabled kinds */
    .kinds-soon {
      display: flex;
      align-items: center;
      gap: 6px;
      flex-wrap: wrap;
      color: var(--secondary-text-color);
      font-size: 0.85em;
    }
    /* Scope band: does this workspace touch the strip? */
    .scope-band {
      display: flex;
      align-items: center;
      gap: 8px;
      padding: 7px 12px;
      border-radius: 8px;
      font-size: 0.85em;
      font-weight: 600;
      background: var(--secondary-background-color);
    }
    .scope-band.live {
      border-left: 3px solid var(--primary-color);
      color: var(--primary-text-color);
    }
    .scope-band.draft {
      border-left: 3px solid var(--secondary-text-color);
      color: var(--secondary-text-color);
    }
    .scope-band .dot {
      width: 9px;
      height: 9px;
      border-radius: 50%;
      flex: 0 0 auto;
    }
    .scope-band.live .dot {
      background: var(--primary-color);
    }
    .scope-band.draft .dot {
      border: 2px solid var(--secondary-text-color);
    }
    /* Horizontal scroll guard for the 15-cell strip on narrow cards */
    .strip-scroll {
      position: relative;
      overflow-x: auto;
    }
    .strip-scroll .strip {
      min-width: 336px;
    }
    .strip-scroll::after {
      content: "›";
      position: absolute;
      top: 0;
      right: 0;
      bottom: 0;
      width: 34px;
      pointer-events: none;
      display: flex;
      align-items: center;
      justify-content: flex-end;
      padding-right: 3px;
      box-sizing: border-box;
      color: var(--primary-color);
      font-size: 24px;
      font-weight: 700;
      background: linear-gradient(
        to left,
        var(--card-background-color) 35%,
        transparent
      );
      opacity: 0;
      transition: opacity 0.15s ease;
    }
    .strip-scroll.clipped::after {
      opacity: 1;
    }
    /* Non-interactive resolved preview strip */
    .strip.preview-strip {
      pointer-events: none;
    }
    /* Gradient track padding so end handles never clip */
    .gradient-track {
      padding: 0 12px;
    }
    /* Library: active row + inline delete confirm */
    .effect .badge-active {
      display: inline-flex;
      align-items: center;
      gap: 4px;
      border-radius: 18px;
      padding: 6px 14px;
      font: inherit;
      font-weight: 600;
      background: transparent;
      color: var(--primary-color);
      border: 1px solid var(--primary-color);
      cursor: default;
    }
    .effect.active {
      border-left: 3px solid var(--primary-color);
      padding-left: 8px;
      border-radius: 4px;
    }
    .effect.quarantined {
      border-left: 3px solid var(--warning-color, #f9a825);
      padding-left: 8px;
      border-radius: 4px;
    }
    .badge-unavailable {
      display: inline-flex;
      align-items: center;
      border-radius: 18px;
      padding: 6px 10px;
      color: var(--warning-color, #f9a825);
      border: 1px solid var(--warning-color, #f9a825);
      font-size: 0.85em;
      font-weight: 600;
    }
    .effect .btn.danger {
      border-color: var(--error-color);
      color: var(--error-color);
    }
    .effect .btn.danger.primary {
      background: var(--error-color);
      color: var(--text-primary-color, #fff);
    }
    .effect .confirm-text {
      flex: 1 1 auto;
      min-width: 0;
      color: var(--primary-text-color);
      font-size: 0.9em;
    }
    @media (max-width: 360px) {
      .cell .cell-num {
        display: none;
      }
      .motion-grid {
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }
      .range-row {
        grid-template-columns: 1fr 4ch;
      }
      .range-row > span {
        grid-column: 1 / -1;
      }
    }
`;class xr extends Z{static properties={hass:{attribute:!1},_config:{state:!0}};setConfig(r){this._config={...r}}render(){return m`
      <div class="editor">
        <ha-entity-picker
          .hass=${this.hass}
          .value=${this._config?.entity??""}
          .includeDomains=${["light"]}
          .label=${"Light entity"}
          allow-custom-entity
          @value-changed=${this._entityChanged}
        ></ha-entity-picker>
        <p class="help">
          Choose a segment-capable Govee light (one exposing a
          <code>segment_colors</code> attribute).
        </p>
      </div>
    `}_entityChanged(r){let w=r.detail?.value??"",u={...this._config,entity:w};this.dispatchEvent(new CustomEvent("config-changed",{detail:{config:u},bubbles:!0,composed:!0}))}static styles=e`
    .editor {
      padding: 8px;
    }
    .help {
      margin: 8px 0 0;
      color: var(--secondary-text-color);
      font-size: 0.85em;
    }
  `}customElements.define("govee-led-ble-card-editor",xr);var sr=[{id:"fade",label:"Fade",family:0,palette_max:8,control_label:"Speed",description:"Uses a Govee Fade pattern with the shared palette.",variants:[{id:"fade-1",label:"Fade1",variant:0},{id:"fade-2",label:"Fade2",variant:1},{id:"fade-3",label:"Fade3",variant:2}]},{id:"jumping",label:"Jumping",family:1,palette_max:8,control_label:"Speed",description:"Uses a Govee Jumping pattern with the shared palette.",variants:[{id:"jumping-1",label:"Jumping1",variant:0},{id:"jumping-2",label:"Jumping2",variant:2}]},{id:"twinkle",label:"Twinkle",family:2,palette_max:8,control_label:"Speed",description:"Uses a Govee Twinkle pattern with the shared palette.",variants:[{id:"twinkle-1",label:"Twinkle1",variant:0},{id:"twinkle-2",label:"Twinkle2",variant:1},{id:"twinkle-3",label:"Twinkle3",variant:2}]},{id:"marquee",label:"Marquee",family:3,palette_max:8,control_label:"Speed",description:"Uses a Govee Marquee pattern with the shared palette.",variants:[{id:"marquee-1",label:"Marquee1",variant:3},{id:"marquee-2",label:"Marquee2",variant:4},{id:"marquee-3",label:"Marquee3",variant:5}]},{id:"music",label:"Music",family:4,palette_max:8,control_label:"Sensitivity",description:"Uses a Govee DIY Music pattern, separate from the light's Music mode.",variants:[{id:"music-1",label:"Music1",variant:8},{id:"music-2",label:"Music2",variant:6},{id:"music-3",label:"Music3",variant:7}]},{id:"chasing",label:"Chasing",family:8,palette_max:8,control_label:"Speed",description:"Uses a Govee Chasing pattern with the shared palette.",variants:[{id:"chasing-1",label:"Chasing1",variant:9},{id:"chasing-2",label:"Chasing2",variant:10}]},{id:"rainbow",label:"Rainbow",family:9,palette_max:8,control_label:"Speed",description:"Uses a Govee Rainbow pattern with the shared palette.",variants:[{id:"rainbow-1",label:"Rainbow1",variant:9},{id:"rainbow-2",label:"Rainbow2",variant:10}]},{id:"crossing",label:"Crossing",family:10,palette_max:3,control_label:"Speed",description:"Uses the single Govee Crossing pattern with up to three colours.",variants:[{id:"crossing",label:"Crossing",variant:0}]}];var C=sr,yw=new Set([0,1,2,3,8,9]),P=C.filter((r)=>yw.has(r.family)),rr=[{code:2,label:"Cycle"},{code:9,label:"Clockwise"},{code:10,label:"Counter-clockwise"},{code:15,label:"Twinkle"},{code:19,label:"Gradient"},{code:20,label:"Breathe"}];function k(r,w){if(r===null||typeof r!=="object"||Array.isArray(r))throw Error(`${w} must be an object.`);return r}function l(r,w){if(typeof r!=="string"||r.trim()==="")throw Error(`${w} must be a non-empty string.`);return r.trim()}function Q(r,w){if(typeof r!=="number"||!Number.isInteger(r))throw Error(`${w} must be an integer.`);return r}function i(r,w){let u=Q(r,w);if(u<0||u>100)throw Error(`${w} must be from 0 to 100.`);return u}function Iw(r,w){let u=Q(r,w);if(u<0||u>255)throw Error(`${w} must be from 0 to 255.`);return u}function A(r,w){if(!Array.isArray(r))throw Error(`${w} must be an array.`);return r}function zr(r,w){let u=A(r,w);if(u.length!==3||u.some((o)=>typeof o!=="number"||!Number.isInteger(o)||o<0||o>255))throw Error(`${w} must contain three channels from 0 to 255.`);return[u[0],u[1],u[2]]}function Ow(r,w){return r===null?null:zr(r,w)}function ar(r,w){return A(r,w).map((u,o)=>zr(u,`${w}[${o}]`))}function er(r,w){return A(r,w).map((u,o)=>Ow(u,`${w}[${o}]`))}function tr(r){let w=k(r,"Effect content"),u=l(w.kind,"Effect kind");switch(u){case"segments":{let o=w.brightness,n=null;if(o!==null)n=A(o,"Segment brightness").map((b,$)=>b===null?null:i(b,`Segment brightness[${$}]`));return{kind:u,colors:er(w.colors,"Segment colours"),brightness:n}}case"vibrant":{let o=ar(w.stops,"Gradient stops");if(o.length<2||o.length>5)throw Error("Gradient stops must contain from 2 to 5 colours.");return{kind:u,stops:o}}case"sketch":{let o=Q(w.motion,"Sketch motion");if(!rr.some((n)=>n.code===o))throw Error("Sketch motion is not supported.");return{kind:u,motion:o,speed:i(w.speed,"Sketch speed"),brightness:i(w.brightness,"Sketch brightness"),background:zr(w.background,"Sketch background"),colors:er(w.colors,"Sketch colours")}}case"flat":{let o=Q(w.family,"Flat family"),n=Q(w.variant,"Flat variant");Zr(o,n);let b=ar(w.palette,"Flat palette"),$=D(o);if(b.length>$.palette_max)throw Error(`${$.label} accepts up to ${$.palette_max} colours.`);return{kind:u,family:o,variant:n,speed:i(w.speed,"Flat speed"),palette:b}}case"combo":{let o=A(w.effects,"Combo effects").map(($,E)=>{let p=A($,`Combo effects[${E}]`);if(p.length!==2)throw Error(`Combo effects[${E}] must contain a family and variant.`);let F=Q(p[0],`Combo effects[${E}].family`),J=Q(p[1],`Combo effects[${E}].variant`);return ur(F,J),[F,J]});if(o.length===0)throw Error("Combo requires at least one step.");if(o.length>4)throw Error("Combo accepts up to four steps.");let n=ar(w.palette,"Combo palette");if(n.length===0)throw Error("Combo requires at least one palette colour.");if(n.length>8)throw Error("Combo accepts up to 8 colours.");let b=Iw(w.variant,"Combo variant");if(b!==0)throw Error("Combo variant must be 0.");return{kind:u,variant:b,speed:i(w.speed,"Combo speed"),palette:n,effects:o}}default:throw Error(`Unsupported effect kind "${u}".`)}}function rw(r){let w=k(r,"Export response"),u=Q(w.segment_count,"Export segment count");if(u<=0)throw Error("Export segment count must be positive.");return{id:l(w.id,"Effect ID"),name:l(w.name,"Effect name"),model:l(w.model,"Effect model"),segment_count:u,content:k(w.content,"Effect content")}}function fw(r){let w=rw(r);return{...w,content:tr(w.content)}}function jr(r,w){let u=k(r,"Entity service response");if(!(w in u))throw Error(`The export response did not include ${w}.`);return fw(u[w])}function ww(r,w){let u=k(r,"Entity service response");if(!(w in u))throw Error(`The export response did not include ${w}.`);return rw(u[w])}function uw(r){return{schema_version:1,integration:"ha_govee_led_ble",source:{model:r.model,segment_count:r.segment_count},effect:{name:r.name,content:r.content}}}function ow(r,w){let u;try{u=JSON.parse(r)}catch{throw Error("This is not valid JSON.")}let o=k(u,"Effect document");if(o.schema_version!==1)throw Error("This effect uses an unsupported schema version.");if(o.integration!=="ha_govee_led_ble")throw Error("This file is not a Govee LED BLE effect.");let n=k(o.source,"Effect source"),b=l(n.model,"Source model"),$=Q(n.segment_count,"Source segment count");if($<=0)throw Error("Source segment count must be positive.");if($!==w.segmentCount)throw Error(`This effect needs ${$} segments; this light has ${w.segmentCount}.`);if(w.model!==null&&w.model!==b)throw Error(`This effect was exported for ${b}; this light is ${w.model}.`);let E=k(o.effect,"Effect"),p=tr(E.content);if((p.kind==="segments"||p.kind==="sketch")&&p.colors.length>$)throw Error(`This effect contains more than ${$} segments.`);if(p.kind==="segments"&&p.brightness!==null&&p.brightness.length>$)throw Error(`This effect contains more than ${$} brightness values.`);return{schema_version:1,integration:"ha_govee_led_ble",source:{model:b,segment_count:$},effect:{name:l(E.name,"Effect name"),content:p}}}function Vr(r){switch(r.kind){case"segments":return"static";case"vibrant":return"gradient";default:return r.kind}}function Yr(r,w,u,o,n){return{kind:"sketch",motion:w,speed:u,brightness:o,background:[n[0],n[1],n[2]],colors:r.map((b)=>b===null?null:[b[0],b[1],b[2]])}}function D(r){let w=C.find((u)=>u.family===r);if(w===void 0)throw Error(`Unknown Flat family ${r}.`);return w}function wr(r){let w=P.find((u)=>u.family===r);if(w===void 0)throw Error(`Flat family ${r} is not available in Combo.`);return w}function nw(r,w,u,o){let n=D(r);if(!n.variants.some((b)=>b.variant===w))throw Error(`Unknown variant for ${n.label}.`);if(o.length===0)throw Error("Add at least one palette colour.");if(o.length>n.palette_max)throw Error(`${n.label} accepts up to ${n.palette_max} colours.`);return{kind:"flat",family:r,variant:w,speed:u,palette:o.map((b)=>[b[0],b[1],b[2]])}}function Zr(r,w){let u=D(r),o=u.variants.find((n)=>n.variant===w);if(o===void 0)throw Error(`Unknown variant for ${u.label}.`);return o.label}function ur(r,w){let u=wr(r),o=u.variants.find((n)=>n.variant===w);if(o===void 0)throw Error(`Unknown Combo variant for ${u.label}.`);return o.label}function bw(r,w,u,o=0){if(o!==0)throw Error("Combo variant must be 0.");if(r.length===0)throw Error("Add at least one Combo step.");if(r.length>4)throw Error("Combo accepts up to four steps.");for(let[n,b]of r)ur(n,b);if(u.length===0)throw Error("Add at least one palette colour.");if(u.length>8)throw Error("Combo accepts up to 8 colours.");return{kind:"combo",variant:o,speed:w,palette:u.map((n)=>[n[0],n[1],n[2]]),effects:r.map(([n,b])=>[n,b])}}function $w(r){let w=Math.max(0,Math.min(100,r.brightness))/100;return r.colors.map((u)=>{return(u??r.background).map((n)=>Math.round(n*w))})}function Qr(r,w){let u=new Set(w.map(c)),o=`${mw(r)} copy`;if(!u.has(c(o)))return o;for(let n=2;;n+=1){let b=`${o} ${n}`;if(!u.has(c(b)))return b}}function mw(r){return r.trim().replace(/^["'“”‘’]+|["'“”‘’]+$/gu,"").trim().replace(/\s+/gu," ")}function c(r){return mw(r).toLocaleLowerCase().replaceAll("ß","ss").replaceAll("ς","σ")}function pw(r,w){let u=r.trim();return w.some((n)=>c(n)===c(u))?Qr(u,w):u}function Ew(r){return`${r.trim().toLocaleLowerCase().replace(/[^a-z0-9]+/g,"-").replace(/^-+|-+$/g,"")||"govee-effect"}.json`}var B=15;function Y(r,w,u){return Math.max(w,Math.min(u,r))}function a(r){let w=r.replace("#","");return[parseInt(w.slice(0,2),16),parseInt(w.slice(2,4),16),parseInt(w.slice(4,6),16)]}function j(r){return"#"+r.map((w)=>Y(Math.round(w),0,255).toString(16).padStart(2,"0")).join("")}function or(r,w){if(r.length===0)throw Error("no stops");if(r.length===1){let p=r[0];return[p[0],p[1],p[2]]}let u=r.length-1,o=Y(w,0,1)*u,n=Y(Math.floor(o),0,u-1),b=o-n,$=r[n],E=r[n+1];return[$[0]+(E[0]-$[0])*b,$[1]+(E[1]-$[1])*b,$[2]+(E[2]-$[2])*b]}function Nw(r){let w=Math.floor(r),u=r-w;if(u<0.5)return w;if(u>0.5)return w+1;return w%2===0?w:w+1}function nr(r,w=15){if(r.length===0)throw Error("no stops");if(w<=0)return[];if(r.length===1){let u=r[0];return Array.from({length:w},()=>[u[0],u[1],u[2]])}return Array.from({length:w},(u,o)=>{let n=w>1?o/(w-1):0;return or(r,n).map(Nw)})}function Dr(r){let w=new Map,u=[];return r.forEach((o,n)=>{let b=`${o[0]},${o[1]},${o[2]}`,$=w.get(b);if($===void 0)$={segments:[],rgb_color:[o[0],o[1],o[2]]},w.set(b,$),u.push($);$.segments.push(n+1)}),u}var Jw=[{id:"sunset",name:"Sunset",stops:[[255,89,94],[255,146,76],[255,202,58]]},{id:"ocean",name:"Ocean",stops:[[15,32,89],[25,130,196],[112,193,179]]},{id:"forest",name:"Forest",stops:[[27,67,50],[45,106,79],[149,213,178]]},{id:"rainbow",name:"Rainbow",stops:[[255,0,0],[255,183,0],[0,200,83],[0,145,234],[170,0,255]]},{id:"warm-white",name:"Warm white",stops:[[255,183,107]]},{id:"cool-white",name:"Cool white",stops:[[188,220,255]]}];function qw(r,w=15){return Dr(nr(r.stops,w))}function Bw(r){return[...new Set(r)].sort((w,u)=>w-u)}function Fw(r,w){let u=Math.min(r,w),o=Math.max(r,w),n=new Set;for(let b=u;b<=o;b++)n.add(b);return n}function Wr(r,w){let u=new Set(r);if(u.has(w))u.delete(w);else u.add(w);return u}function Rw(r=15){let w=new Set;for(let u=1;u<=r;u++)w.add(u);return w}function g(){return new Set}function br(r){if(r===null||typeof r!=="object"||Array.isArray(r))return[];let w=[];for(let[u,o]of Object.entries(r)){if(typeof o!=="string")continue;let n=o.trim();if(n==="")continue;w.push({id:u,name:n})}return w.sort((u,o)=>{let n=u.name.toLowerCase(),b=o.name.toLowerCase();if(n!==b)return n<b?-1:1;if(u.id!==o.id)return u.id<o.id?-1:1;return 0}),w}var U=[{id:"now",label:"Now"},{id:"studio",label:"Studio"},{id:"library",label:"Library"}];function y(r,w,u){if(u<=0)return r;switch(w){case"ArrowRight":case"ArrowDown":return(r+1)%u;case"ArrowLeft":case"ArrowUp":return(r-1+u)%u;case"Home":return 0;case"End":return u-1;default:return r}}var I=[{id:"static",label:"Static",available:!0},{id:"gradient",label:"Gradient",available:!0},{id:"sketch",label:"Sketch",available:!0},{id:"flat",label:"Flat",available:!0},{id:"combo",label:"Combo",available:!0}],Sw={static:"segments",gradient:"vibrant",sketch:"sketch",flat:"flat",combo:"combo"};function aw(r){let w=I.filter((o)=>o.available);if(!Array.isArray(r))return w.map((o)=>o.id);let u=new Set(r.filter((o)=>typeof o==="string"));return w.filter((o)=>u.has(Sw[o.id])).map((o)=>o.id)}function zw(r,w=null){let u=w!==null&&w.some((o)=>o!==null);return{kind:"segments",colors:r.map((o)=>o===null?null:[o[0],o[1],o[2]]),brightness:u?w.map((o)=>o===null?null:o):null}}function jw(r,w=null){return r.some((u)=>u!==null)||w!==null&&w.some((u)=>u!==null)}function Vw(r){return{kind:"vibrant",stops:r.map((w)=>[w[0],w[1],w[2]])}}function Cr(r){if(r!==null&&typeof r==="object"){let w=r.message;if(typeof w==="string"&&w.trim()!=="")return w}return null}function V(r,w="Something went wrong."){if(typeof r==="string"&&r.trim()!=="")return r;let u=Cr(r);if(u!==null)return u;if(r!==null&&typeof r==="object"){let o=r,n=Cr(o.error)??Cr(o.body);if(n!==null)return n}return w}var h=["#ff595e","#ffca3a","#1982c4"],kr="#33cc66",gr=2,Gr=5,Yw="Govee Effect Studio",Zw=I.filter((r)=>!r.available);function vw(r){if(!Array.isArray(r))return null;let w=[];for(let u of r){if(!Array.isArray(u)||u.length<3)return null;let[o,n,b]=u;if(typeof o!=="number"||typeof n!=="number"||typeof b!=="number")return null;w.push([o,n,b])}return w}function dw(r,w){let u=window.document.createElement("a");return u.download=r,u.href=w,u}class Qw extends Z{static properties={hass:{attribute:!1},_config:{state:!0},_tab:{state:!0},_studioKind:{state:!0},_selection:{state:!0},_cursor:{state:!0},_paintColor:{state:!0},_staticColors:{state:!0},_staticBrightness:{state:!0},_sketchColors:{state:!0},_sketchMotion:{state:!0},_sketchSpeed:{state:!0},_sketchBrightness:{state:!0},_sketchBackground:{state:!0},_flatFamily:{state:!0},_flatVariant:{state:!0},_flatSpeed:{state:!0},_flatPalette:{state:!0},_comboEffects:{state:!0},_comboVariant:{state:!0},_comboSpeed:{state:!0},_comboPalette:{state:!0},_stops:{state:!0},_studioStops:{state:!0},_dragStop:{state:!0},_dragFrac:{state:!0},_effectName:{state:!0},_studioName:{state:!0},_editingId:{state:!0},_loadedContent:{state:!0},_pendingDraft:{state:!0},_importText:{state:!0},_busyKey:{state:!0},_renamingId:{state:!0},_renameValue:{state:!0},_deletingId:{state:!0},_feedback:{state:!0}};_dragging=!1;_dragAnchor=1;_touchStart=null;_ro;_draftBaseline="";_editingOriginalName=null;_editingOriginalContent=null;constructor(){super();this._tab="now",this._studioKind="static",this._selection=new Set,this._cursor=1,this._paintColor=kr,this._staticColors=Array.from({length:B},()=>null),this._staticBrightness=null,this._sketchColors=Array.from({length:B},()=>null),this._sketchMotion=9,this._sketchSpeed=51,this._sketchBrightness=100,this._sketchBackground="#000000",this._flatFamily=C[0].family,this._flatVariant=C[0].variants[0].variant,this._flatSpeed=50,this._flatPalette=[...h],this._comboEffects=[{family:P[0].family,variant:P[0].variants[0].variant}],this._comboVariant=0,this._comboSpeed=51,this._comboPalette=[...h],this._stops=[...h],this._studioStops=[...h],this._dragStop=null,this._dragFrac=null,this._effectName="",this._studioName="",this._editingId=null,this._loadedContent=null,this._pendingDraft=null,this._importText="",this._busyKey=null,this._renamingId=null,this._renameValue="",this._deletingId=null,this._feedback=null,this._draftBaseline=this._draftSignature()}static getStubConfig(r){return{entity:(r?Object.keys(r.states).find((u)=>u.startsWith("light.")&&Array.isArray(r.states[u].attributes?.segment_colors)):void 0)??""}}static getConfigElement(){return document.createElement("govee-led-ble-card-editor")}setConfig(r){if(!r)throw Error("Invalid configuration");this._config={...r}}getCardSize(){return 12}connectedCallback(){super.connectedCallback(),this._ro=new ResizeObserver(()=>{this._updateClipped(),this._drawNowPreview()}),this._ro.observe(this)}disconnectedCallback(){super.disconnectedCallback(),this._ro?.disconnect(),window.removeEventListener("pointermove",this._onMove),window.removeEventListener("pointerup",this._onUp),window.removeEventListener("pointercancel",this._onUp),window.removeEventListener("pointerup",this._onTouchUp),window.removeEventListener("pointercancel",this._onTouchCancel),window.removeEventListener("pointermove",this._onStopMove),window.removeEventListener("pointerup",this._onStopUp)}updated(){this._ensureSupportedStudioKind(),this._reconcileDraftIds(),this._updateClipped(),this._drawNowPreview()}_reconcileDraftIds(){let r=this._config?.entity,w=r?this.hass?.states[r]:void 0;if(!w)return;let u=br(w.attributes?.custom_effects),o=new Set(u.map((n)=>n.id));if(this._editingId!==null){let n=u.find((b)=>b.id===this._editingId);if(n===void 0)this._editingId=null,this._editingOriginalName=null,this._editingOriginalContent=null,this._draftBaseline="",this._feedback={kind:"info",text:"The saved effect was removed elsewhere. Its Studio draft is now a new effect."};else if(this._editingOriginalName!==null&&this._studioName.trim()===this._editingOriginalName&&n.name!==this._editingOriginalName){let b=this._currentContentSignature()===this._editingOriginalContent;if(this._studioName=n.name,this._editingOriginalName=n.name,b)this._draftBaseline=this._draftSignature()}}if(this._pendingDraft?.editingId!==null&&this._pendingDraft?.editingId!==void 0&&!o.has(this._pendingDraft.editingId))this._pendingDraft={...this._pendingDraft,editingId:null,feedback:"The saved effect was removed elsewhere. Its loaded content will open as a new draft."}}_updateClipped(){for(let r of this.renderRoot.querySelectorAll(".strip-scroll"))r.classList.toggle("clipped",r.scrollWidth>r.clientWidth+1)}_selectTab(r){if(this._tab===r)return;this._tab=r,this._selection=g(),this._cursor=1}_onTabKey(r){let w=U.findIndex((o)=>o.id===this._tab),u=y(w,r.key,U.length);if(u===w)return;r.preventDefault(),this._selectTab(U[u].id),this.updateComplete.then(()=>{this.renderRoot.querySelector(`#tab-${U[u].id}`)?.focus()})}_draftSignature(){let r={kind:this._studioKind,name:this._studioName};switch(this._studioKind){case"static":return JSON.stringify({...r,colors:this._staticColors,brightness:this._staticBrightness});case"gradient":return JSON.stringify({...r,stops:this._studioStops});case"sketch":return JSON.stringify({...r,colors:this._sketchColors,motion:this._sketchMotion,speed:this._sketchSpeed,brightness:this._sketchBrightness,background:this._sketchBackground});case"flat":return JSON.stringify({...r,family:this._flatFamily,variant:this._flatVariant,speed:this._flatSpeed,palette:this._flatPalette});case"combo":return JSON.stringify({...r,effects:this._comboEffects,variant:this._comboVariant,speed:this._comboSpeed,palette:this._comboPalette})}}_hasUnsavedDraft(){return this._draftSignature()!==this._draftBaseline}_selectKind(r){if(!this._supportedStudioKinds().includes(r))return;if(this._editingId!==null&&r!==this._studioKind)return;let w=this._hasUnsavedDraft();if(this._studioKind=r,this._loadedContent=null,!w&&this._editingId===null)this._draftBaseline=this._draftSignature()}_onKindKey(r){if(this._editingId!==null)return;let w=this._availableKindDescriptors(),u=w.findIndex((n)=>n.id===this._studioKind),o=y(u,r.key,w.length);if(o===u)return;r.preventDefault(),this._selectKind(w[o].id),this.updateComplete.then(()=>{this.renderRoot.querySelector('.kinds .kind[aria-checked="true"]')?.focus()})}_focusChecked(r){this.updateComplete.then(()=>{this.renderRoot.querySelector(`${r}[aria-checked="true"]`)?.focus()})}_onMotionKey(r){let w=rr.map((n)=>n.code),u=w.indexOf(this._sketchMotion),o=y(u,r.key,w.length);if(o===u)return;r.preventDefault(),this._sketchMotion=w[o],this._focusChecked(".motion")}_onFlatFamilyKey(r){let w=C.map((n)=>n.family),u=w.indexOf(this._flatFamily),o=y(u,r.key,w.length);if(o===u)return;r.preventDefault(),this._selectFlatFamily(w[o]),this._focusChecked(".family")}_onFlatVariantKey(r){let w=D(this._flatFamily).variants.map((n)=>n.variant),u=w.indexOf(this._flatVariant),o=y(u,r.key,w.length);if(o===u)return;r.preventDefault(),this._flatVariant=w[o],this._focusChecked(".variant")}_segmentColors(){let r=this._config?.entity;if(!r||!this.hass)return null;let w=this.hass.states[r];if(!w)return null;return vw(w.attributes?.segment_colors)}_supportedStudioKinds(){let r=this._config?.entity,w=r?this.hass?.states[r]?.attributes?.custom_effect_kinds:void 0;return aw(w)}_availableKindDescriptors(){let r=new Set(this._supportedStudioKinds());return I.filter((w)=>w.available&&r.has(w.id))}_isStudioKindSupported(r){return this._supportedStudioKinds().includes(r)}_ensureSupportedStudioKind(){if(this._isStudioKindSupported(this._studioKind))return;let[r]=this._supportedStudioKinds();if(r===void 0)return;this._editingId=null,this._editingOriginalName=null,this._editingOriginalContent=null,this._loadedContent=null,this._studioKind=r,this._draftBaseline=this._draftSignature()}_cellFromClientX(r){let w=this.renderRoot.querySelector(".strip");if(!w)return 1;let u=w.getBoundingClientRect(),o=u.width/B;return Y(Math.floor((r-u.left)/o),0,B-1)+1}_onDown(r){if(r.pointerType==="touch"){this._touchStart={x:r.clientX,y:r.clientY,cell:this._cellFromClientX(r.clientX)},window.addEventListener("pointerup",this._onTouchUp),window.addEventListener("pointercancel",this._onTouchCancel);return}r.preventDefault(),this._dragging=!0,this._dragAnchor=this._cellFromClientX(r.clientX),this._cursor=this._dragAnchor,this._selection=new Set([this._dragAnchor]),this.renderRoot.querySelector(".strip")?.focus(),window.addEventListener("pointermove",this._onMove),window.addEventListener("pointerup",this._onUp),window.addEventListener("pointercancel",this._onUp)}_onMove=(r)=>{if(!this._dragging)return;let w=this._cellFromClientX(r.clientX);this._selection=Fw(this._dragAnchor,w),this._cursor=w};_onUp=()=>{this._dragging=!1,window.removeEventListener("pointermove",this._onMove),window.removeEventListener("pointerup",this._onUp),window.removeEventListener("pointercancel",this._onUp)};_onTouchUp=(r)=>{let w=this._touchStart;if(this._clearTouchGesture(),w===null||Math.hypot(r.clientX-w.x,r.clientY-w.y)>10)return;this._cursor=w.cell,this._selection=Wr(this._selection,w.cell)};_onTouchCancel=()=>{this._clearTouchGesture()};_clearTouchGesture(){this._touchStart=null,window.removeEventListener("pointerup",this._onTouchUp),window.removeEventListener("pointercancel",this._onTouchCancel)}_onKey(r){let w=r.key,u=["ArrowRight","ArrowDown","ArrowLeft","ArrowUp","Home","End"];if(w==="ArrowRight"||w==="ArrowDown")this._cursor=Y(this._cursor+1,1,B),r.preventDefault();else if(w==="ArrowLeft"||w==="ArrowUp")this._cursor=Y(this._cursor-1,1,B),r.preventDefault();else if(w==="Home")this._cursor=1,r.preventDefault();else if(w==="End")this._cursor=B,r.preventDefault();else if(w===" "||w==="Spacebar")this._selection=Wr(this._selection,this._cursor),r.preventDefault();else if(w==="Enter"){if(this._tab==="studio")this._paintActiveDraft();else this._applyPaint();r.preventDefault()}else if(w==="Escape")this._dragging=!1,this._selection=g(),r.preventDefault();if(u.includes(w))this._scrollCursorIntoView()}_scrollCursorIntoView(){this.updateComplete.then(()=>{this.renderRoot.querySelector(".cell.cursor")?.scrollIntoView({inline:"nearest",block:"nearest"})})}_selectAll(){this._selection=Rw(B)}_clear(){this._selection=g()}_applyPaint(){let r=this._config?.entity;if(!this.hass||!r||this._selection.size===0)return;let w=[{segments:Bw(this._selection),rgb_color:a(this._paintColor)}];this.hass.callService("ha_govee_led_ble","paint_segments",{groups:w},{entity_id:r})}_paintStatic(){if(this._selection.size===0)return;let r=[...this._staticColors];for(let w of this._selection)r[w-1]=this._paintColor;this._staticColors=r}_paintSketch(){if(this._selection.size===0)return;let r=[...this._sketchColors];for(let w of this._selection)r[w-1]=this._paintColor;this._sketchColors=r}_paintActiveDraft(){if(this._studioKind==="sketch")this._paintSketch();else this._paintStatic()}_setUnchangedStatic(){if(this._selection.size===0)return;let r=[...this._staticColors];for(let w of this._selection)r[w-1]=null;this._staticColors=r}_clearSketchSelection(){if(this._selection.size===0)return;let r=[...this._sketchColors];for(let w of this._selection)r[w-1]=null;this._sketchColors=r}_resetStatic(){this._staticColors=Array.from({length:B},()=>null),this._staticBrightness=null,this._selection=g(),this._finishDraftReset()}_resetSketch(){this._sketchColors=Array.from({length:B},()=>null),this._sketchMotion=9,this._sketchSpeed=51,this._sketchBrightness=100,this._sketchBackground="#000000",this._selection=g(),this._finishDraftReset()}_selectFlatFamily(r){let w=D(r);if(this._flatPalette.length>w.palette_max){this._feedback={kind:"error",text:`${w.label} accepts up to ${w.palette_max} colours. Remove some first.`};return}this._flatFamily=r,this._flatVariant=w.variants[0].variant,this._feedback=null}_setFlatPaletteColour(r,w){let u=[...this._flatPalette];u[r]=w,this._flatPalette=u}_addFlatPaletteColour(){let r=D(this._flatFamily).palette_max;if(this._flatPalette.length>=r)return;this._flatPalette=[...this._flatPalette,kr]}_removeFlatPaletteColour(r){if(this._flatPalette.length<=1)return;this._flatPalette=this._flatPalette.filter((w,u)=>u!==r)}_moveFlatPaletteColour(r,w){let u=r+w;if(u<0||u>=this._flatPalette.length)return;let o=[...this._flatPalette];[o[r],o[u]]=[o[u],o[r]],this._flatPalette=o}_resetFlat(){this._flatFamily=C[0].family,this._flatVariant=C[0].variants[0].variant,this._flatSpeed=50,this._flatPalette=[...h],this._finishDraftReset()}_setComboFamily(r,w){let u=wr(w);this._comboEffects=this._comboEffects.map((o,n)=>n===r?{family:w,variant:u.variants[0].variant}:o)}_setComboVariant(r,w){let u=this._comboEffects[r];ur(u.family,w),this._comboEffects=this._comboEffects.map((o,n)=>n===r?{...o,variant:w}:o)}_addComboStep(){if(this._comboEffects.length>=4)return;let r=P[0];this._comboEffects=[...this._comboEffects,{family:r.family,variant:r.variants[0].variant}]}_removeComboStep(r){if(this._comboEffects.length<=1)return;this._comboEffects=this._comboEffects.filter((w,u)=>u!==r)}_moveComboStep(r,w){let u=r+w;if(u<0||u>=this._comboEffects.length)return;let o=[...this._comboEffects];[o[r],o[u]]=[o[u],o[r]],this._comboEffects=o}_setComboPaletteColour(r,w){let u=[...this._comboPalette];u[r]=w,this._comboPalette=u}_addComboPaletteColour(){if(this._comboPalette.length>=8)return;this._comboPalette=[...this._comboPalette,kr]}_removeComboPaletteColour(r){if(this._comboPalette.length<=1)return;this._comboPalette=this._comboPalette.filter((w,u)=>u!==r)}_moveComboPaletteColour(r,w){let u=r+w;if(u<0||u>=this._comboPalette.length)return;let o=[...this._comboPalette];[o[r],o[u]]=[o[u],o[r]],this._comboPalette=o}_resetCombo(){let r=P[0];this._comboEffects=[{family:r.family,variant:r.variants[0].variant}],this._comboVariant=0,this._comboSpeed=51,this._comboPalette=[...h],this._finishDraftReset()}_finishDraftReset(){if(this._editingId===null)this._draftBaseline=this._draftSignature()}_activeStops(){return this._tab==="studio"?this._studioStops:this._stops}_setActiveStops(r){if(this._tab==="studio")this._studioStops=r;else this._stops=r}_addStop(){let r=this._activeStops();if(r.length>=Gr)return;let w=or(r.map(a),0.5);this._setActiveStops([...r,j(w)])}_removeStop(r){let w=this._activeStops();if(w.length<=gr)return;this._setActiveStops(w.filter((u,o)=>o!==r))}_moveStop(r,w){let u=r+w,o=this._activeStops();if(u<0||u>=o.length)return;let n=[...o];[n[r],n[u]]=[n[u],n[r]],this._setActiveStops(n)}_recolourStop(r,w){let u=[...this._activeStops()];u[r]=w,this._setActiveStops(u)}_stopTargetIndex(r){let w=this.renderRoot.querySelector(".gradient-bar"),u=this._activeStops();if(!w)return this._dragStop??0;let o=w.getBoundingClientRect(),n=Y((r-o.left)/o.width,0,1);return Y(Math.round(n*(u.length-1)),0,u.length-1)}_startStopDrag(r,w){r.preventDefault(),this._dragStop=w,window.addEventListener("pointermove",this._onStopMove),window.addEventListener("pointerup",this._onStopUp)}_onStopMove=(r)=>{if(this._dragStop===null)return;let w=this.renderRoot.querySelector(".gradient-bar");if(!w)return;let u=w.getBoundingClientRect();this._dragFrac=Y((r.clientX-u.left)/u.width,0,1)};_onStopUp=(r)=>{if(this._dragStop===null)return;let w=this._dragStop,u=this._stopTargetIndex(r.clientX);if(w!==u){let o=[...this._activeStops()],[n]=o.splice(w,1);o.splice(u,0,n),this._setActiveStops(o)}this._dragStop=null,this._dragFrac=null,window.removeEventListener("pointermove",this._onStopMove),window.removeEventListener("pointerup",this._onStopUp)};_applyGradient(){let r=this._config?.entity;if(!this.hass||!r)return;let w=Dr(nr(this._stops.map(a),B));this.hass.callService("ha_govee_led_ble","paint_segments",{groups:w},{entity_id:r})}_applyPreset(r){let w=this._config?.entity;if(!this.hass||!w)return;this.hass.callService("ha_govee_led_ble","paint_segments",{groups:qw(r)},{entity_id:w})}_presetSwatch(r){if(r.length===1){let[u,o,n]=r[0];return`rgb(${u},${o},${n})`}return`linear-gradient(90deg, ${r.map(([u,o,n],b)=>`rgb(${u},${o},${n}) ${b/(r.length-1)*100}%`).join(", ")})`}async _saveCurrent(){let r=this._config?.entity;if(!this.hass||!r)return;let w=this._effectName.trim();try{await this.hass.callService("ha_govee_led_ble","save_effect",{name:w,capture_current:!0},{entity_id:r}),this._effectName="",this._feedback={kind:"info",text:`Saved "${w}".`}}catch(u){this._feedback={kind:"error",text:V(u)}}}_currentStudioContent(){if(this._studioKind==="static")return zw(this._staticColors.map((r)=>r===null?null:a(r)),this._staticBrightness);if(this._studioKind==="gradient")return Vw(this._studioStops.map(a));if(this._studioKind==="sketch")return Yr(this._sketchColors.map((r)=>r===null?null:a(r)),this._sketchMotion,this._sketchSpeed,this._sketchBrightness,a(this._sketchBackground));if(this._studioKind==="flat")return nw(this._flatFamily,this._flatVariant,this._flatSpeed,this._flatPalette.map(a));if(this._studioKind==="combo")return bw(this._comboEffects.map((r)=>[r.family,r.variant]),this._comboSpeed,this._comboPalette.map(a),this._comboVariant);throw Error(`The ${this._studioKind} editor is not available yet.`)}_currentContentSignature(){try{return JSON.stringify(this._currentStudioContent())}catch{return null}}_targetModel(){let r=this._config?.entity;if(!r||!this.hass)return null;let w=this.hass.entities?.[r]?.device_id;if(!w)return null;return this.hass.devices?.[w]?.model??null}_knownEffectNames(r){let w=this._config?.entity,u=w?this.hass?.states[w]?.attributes?.effect_list:void 0;return[...Array.isArray(u)?u.filter((n)=>typeof n==="string"):[],...r.map((n)=>n.name)]}_loadDraft(r,w,u){if(this._editingId=u,this._loadedContent=w,this._studioName=r,this._studioKind=Vr(w),this._selection=g(),this._cursor=1,w.kind==="segments")this._staticColors=Array.from({length:B},(o,n)=>{let b=w.colors[n];return b===void 0||b===null?null:j(b)}),this._staticBrightness=w.brightness===null?null:Array.from({length:B},(o,n)=>w.brightness?.[n]??null);else if(w.kind==="vibrant")this._studioStops=w.stops.map(j);else if(w.kind==="sketch")this._sketchColors=Array.from({length:B},(o,n)=>{let b=w.colors[n];return b===void 0||b===null?null:j(b)}),this._sketchMotion=w.motion,this._sketchSpeed=w.speed,this._sketchBrightness=w.brightness,this._sketchBackground=j(w.background);else if(w.kind==="flat")D(w.family),this._flatFamily=w.family,this._flatVariant=w.variant,this._flatSpeed=w.speed,this._flatPalette=w.palette.map(j);else if(w.kind==="combo"){for(let[o,n]of w.effects)Zr(o,n);this._comboEffects=w.effects.map(([o,n])=>({family:o,variant:n})),this._comboVariant=w.variant,this._comboSpeed=w.speed,this._comboPalette=w.palette.map(j)}this._tab="studio",this._pendingDraft=null,this._editingOriginalName=u===null?null:r.trim(),this._editingOriginalContent=u===null?null:JSON.stringify(w),this._draftBaseline=u===null?"":this._draftSignature()}_resetStudioDraft(){this._editingId=null,this._editingOriginalName=null,this._editingOriginalContent=null,this._loadedContent=null,this._studioName="",this._staticColors=Array.from({length:B},()=>null),this._staticBrightness=null,this._studioStops=[...h],this._resetSketch(),this._resetFlat(),this._resetCombo(),this._selection=g(),this._cursor=1,this._pendingDraft=null,this._draftBaseline=this._draftSignature()}_cancelEdit(){this._resetStudioDraft(),this._feedback={kind:"info",text:"Edit cancelled."}}_offerDraft(r,w,u,o,n=!1){let b=Vr(w);if(!this._isStudioKindSupported(b)){this._feedback={kind:"error",text:`This light does not support ${I.find(($)=>$.id===b)?.label??b} effects.`};return}if(this._hasUnsavedDraft()){this._pendingDraft={name:r,content:w,editingId:u,feedback:o,clearImport:n},this.updateComplete.then(()=>{this.renderRoot.querySelector(".keep-draft")?.focus()});return}if(this._loadDraft(r,w,u),n)this._importText="";this._feedback={kind:"info",text:o}}_confirmDraftReplacement(){let r=this._pendingDraft;if(r===null)return;if(this._loadDraft(r.name,r.content,r.editingId),r.clearImport)this._importText="";this._feedback={kind:"info",text:r.feedback}}_keepDraft(){this._pendingDraft=null,this._feedback={kind:"info",text:"Kept the existing Studio draft."}}async _saveStudio(){let r=this._config?.entity;if(!this.hass||!r)return;if(!this._isStudioKindSupported(this._studioKind)){this._feedback={kind:"error",text:"This effect type is not supported by this light."};return}let w=this._studioName.trim();try{let u=this._currentStudioContent(),o=this._editingId;if(o===null)await this.hass.callService("ha_govee_led_ble","save_effect",{name:w,content:u},{entity_id:r}),this._feedback={kind:"info",text:`Saved "${w}".`};else{let n={id:o};if(this._editingOriginalName===null||w!==this._editingOriginalName)n.name=w;if(this._editingOriginalContent===null||JSON.stringify(u)!==this._editingOriginalContent)n.content=u;if(Object.keys(n).length===1){this._feedback={kind:"info",text:"No changes to update."};return}await this.hass.callService("ha_govee_led_ble","update_effect",n,{entity_id:r}),this._feedback={kind:"info",text:`Updated "${w}".`}}this._resetStudioDraft()}catch(u){this._feedback={kind:"error",text:V(u)}}}async _readEffect(r,w,u){let o=this._config?.entity;if(!this.hass||!o)throw Error("The light is unavailable.");this._busyKey=`${w}:${r.id}`;try{let n=await this.hass.callService("ha_govee_led_ble","export_effect",{id:r.id},{entity_id:o},!0,!0);return u(n.response,o)}finally{this._busyKey=null}}async _editEffect(r){this._feedback=null;try{let w=await this._readEffect(r,"edit",jr);this._offerDraft(w.name,w.content,w.id,`Editing "${w.name}".`)}catch(w){this._feedback={kind:"error",text:V(w)}}}async _duplicateEffect(r,w){this._feedback=null;try{let u=await this._readEffect(r,"duplicate",jr),o=Qr(u.name,this._knownEffectNames(w));this._offerDraft(o,u.content,null,`Loaded "${o}" as a new draft. Review it, then save.`)}catch(u){this._feedback={kind:"error",text:V(u)}}}async _exportEffect(r){this._feedback=null;try{let w=await this._readEffect(r,"export",ww),u=uw(w),o=new Blob([`${JSON.stringify(u,null,2)}
`],{type:"application/json"}),n=URL.createObjectURL(o),b=dw(Ew(w.name),n);window.document.body.append(b),b.click(),b.remove(),URL.revokeObjectURL(n),this._feedback={kind:"info",text:`Exported "${w.name}".`}}catch(w){this._feedback={kind:"error",text:V(w)}}}_chooseImportFile(){this.renderRoot.querySelector(".import-file")?.click()}async _loadImportFile(r){let w=r.target,u=w.files?.[0];if(w.value="",!u)return;try{this._importText=await u.text(),this._feedback={kind:"info",text:`Loaded ${u.name}. Review the JSON, then import it.`}}catch(o){this._feedback={kind:"error",text:V(o,"Could not read that file.")}}}_reviewImport(r){let w=this._segmentColors()?.length??B;try{let u=ow(this._importText,{model:this._targetModel(),segmentCount:w}),o=pw(u.effect.name,this._knownEffectNames(r));this._offerDraft(o,u.effect.content,null,o===u.effect.name?`Imported "${o}" as a draft. Review it, then save.`:`Imported as "${o}" because that name already exists. Review it, then save.`,!0)}catch(u){this._feedback={kind:"error",text:V(u,"Could not import that effect.")}}}async _applyEffect(r){let w=this._config?.entity;if(!this.hass||!w)return;this._feedback=null;try{await this.hass.callService("light","turn_on",{effect:r.name},{entity_id:w})}catch(u){this._feedback={kind:"error",text:V(u)}}}_startRename(r){this._feedback=null,this._deletingId=null,this._renamingId=r.id,this._renameValue=r.name,this.updateComplete.then(()=>{let w=this.renderRoot.querySelector(".rename-input");w?.focus(),w?.select()})}_cancelRename(){this._renamingId=null,this._renameValue=""}async _commitRename(r){let w=this._config?.entity;if(!this.hass||!w)return;let u=this._renameValue.trim();try{if(await this.hass.callService("ha_govee_led_ble","rename_effect",{id:r.id,to:u},{entity_id:w}),this._editingId===r.id&&this._editingOriginalName!==null&&this._studioName.trim()===this._editingOriginalName){let o=this._currentContentSignature()===this._editingOriginalContent;if(this._studioName=u,this._editingOriginalName=u,o)this._draftBaseline=this._draftSignature()}this._renamingId=null,this._renameValue="",this._feedback={kind:"info",text:`Renamed to "${u}".`}}catch(o){this._feedback={kind:"error",text:V(o)}}}_askDelete(r){if(this._feedback=null,this._renamingId===r.id)this._cancelRename();this._deletingId=r.id,this.updateComplete.then(()=>{this.renderRoot.querySelector(".confirm-cancel")?.focus()})}_cancelDelete(){this._deletingId=null}_onDeleteKey(r){if(r.key==="Escape")r.preventDefault(),this._cancelDelete()}async _deleteEffect(r){let w=this._config?.entity;if(!this.hass||!w)return;this._deletingId=null;try{if(await this.hass.callService("ha_govee_led_ble","delete_effect",{id:r.id},{entity_id:w}),this._editingId===r.id)this._editingId=null,this._editingOriginalName=null,this._editingOriginalContent=null,this._draftBaseline="",this._feedback={kind:"info",text:`Deleted "${r.name}". Its Studio draft was kept as a new effect.`};else this._feedback={kind:"info",text:`Deleted "${r.name}".`};if(this._pendingDraft?.editingId===r.id)this._pendingDraft={...this._pendingDraft,editingId:null,feedback:`Loaded "${r.name}" as a new draft because the saved effect was deleted.`}}catch(u){this._feedback={kind:"error",text:V(u)}}}_onSaveKey(r,w){if(r.key==="Enter")r.preventDefault(),w()}_onRenameKey(r,w){if(r.key==="Enter")r.preventDefault(),this._commitRename(w);else if(r.key==="Escape")r.preventDefault(),this._cancelRename()}_drawNowPreview(){let r=this.renderRoot?.querySelector("canvas.preview");if(r)this._draw(r)}_draw(r){let w=window.devicePixelRatio||1,u=r.clientWidth||480,o=r.clientHeight||44;if(r.width!==Math.round(u*w))r.width=Math.round(u*w),r.height=Math.round(o*w);let n=r.getContext("2d");if(!n)return;n.setTransform(w,0,0,w,0,0),n.clearRect(0,0,u,o);let b=this._stops.map(a),$=B,E=3,p=(u-E*($-1))/$;for(let F=0;F<$;F++){let J=or(b,F/($-1));n.fillStyle=`rgb(${J.map((z)=>Math.round(z)).join(",")})`;let R=F*(p+E);n.beginPath(),n.roundRect(R,0,p,o,4),n.fill()}}render(){if(!this._config)return q;let r=this._config.entity;if(!r)return this._notice("Select a light entity in the card configuration.");let w=this.hass?.states?.[r];if(!w||w.state==="unavailable"||w.state==="unknown")return this._notice(`${r} is unavailable.`);let u=this._segmentColors();if(!u)return this._notice(`${r} exposes no segment colours; this model has no addressable segments.`);return m`
      <ha-card>
        ${this._renderHeader(w)}
        <div class="body">
          ${this._tab==="now"?this._renderNow(u):q}
          ${this._tab==="studio"?this._renderStudio():q}
          ${this._tab==="library"?this._renderLibrary(w):q}
        </div>
      </ha-card>
    `}_notice(r){return m`
      <ha-card header=${Yw}>
        <div class="notice">${r}</div>
      </ha-card>
    `}_renderHeader(r){let w=typeof r.attributes?.effect==="string"&&r.attributes.effect!==""?r.attributes.effect:r.state==="on"?"Colour":"Off";return m`
      <div class="card-head">
        <div class="title">${Yw}</div>
        <div class="status">
          <span>Current:</span>
          <span class="current">${w}</span>
        </div>
        <div class="tabs" role="tablist" aria-label="Effect Studio sections">
          ${U.map((u)=>m`
              <button
                class="tab ${this._tab===u.id?"active":""}"
                id=${`tab-${u.id}`}
                role="tab"
                aria-selected=${this._tab===u.id?"true":"false"}
                aria-controls=${`panel-${u.id}`}
                tabindex=${this._tab===u.id?"0":"-1"}
                @click=${()=>this._selectTab(u.id)}
                @keydown=${this._onTabKey}
              >
                ${u.label}
              </button>
            `)}
        </div>
        ${this._feedback?m`<div class="feedback ${this._feedback.kind}" role="alert">
              ${this._feedback.text}
            </div>`:q}
        ${this._pendingDraft?m`
              <div class="draft-confirm" role="alertdialog" aria-label="Replace Studio draft">
                <span>Replace your unsaved Studio draft with "${this._pendingDraft.name}"?</span>
                <div class="row">
                  <button class="btn keep-draft" @click=${this._keepDraft}>Keep draft</button>
                  <button class="btn primary" @click=${this._confirmDraftReplacement}>
                    Replace draft
                  </button>
                </div>
              </div>
            `:q}
      </div>
    `}_renderScopeBand(r){return m`
      <div class="scope-band ${r}" role="note">
        <span class="dot" aria-hidden="true"></span>
        <span>${r==="live"?"Applies to the strip — changes show instantly":"Draft — builds a saved effect and never changes the strip"}</span>
      </div>
    `}_renderNow(r){let w=Array.from({length:B},(u,o)=>{let n=r[o];return n?j(n):null});return m`
      <div id="panel-now" role="tabpanel" aria-labelledby="tab-now">
        ${this._renderScopeBand("live")}
        <section>
          <div class="row heading">
            <span class="label">Segment painter</span>
            <span class="hint">${this._selection.size} selected</span>
          </div>
          ${this._renderStrip(w,"off")}
          <div class="row controls">
            <input
              type="color"
              aria-label="Paint colour"
              .value=${this._paintColor}
              @input=${(u)=>this._paintColor=u.target.value}
            />
            <button class="btn primary" @click=${this._applyPaint}>
              Apply to selection
            </button>
            <button class="btn" @click=${this._selectAll}>Select all</button>
            <button class="btn" @click=${this._clear}>Clear</button>
          </div>
        </section>
        ${this._renderGradient()}
        ${this._renderPresets()}
        ${this._renderSaveCurrent()}
      </div>
    `}_renderStrip(r,w,u=null){let o=(b)=>`segment-cell-${this._tab}-${this._studioKind}-${b}`,n=[];for(let b=1;b<=B;b++){let $=r[b-1]??null,E=this._selection.has(b),p=b===this._cursor,F=$?"painted":w==="off"?"off":w==="background"?"background":"unchanged",J=$?`background:${$}`:w==="background"&&u!==null?`--cell-background:${u}`:"";n.push(m`
        <div
          id=${o(b)}
          class="cell ${E?"sel":""} ${p?"cursor":""} ${$?"":w}"
          style=${J}
          role="option"
          aria-selected=${E?"true":"false"}
          aria-label=${`Segment ${b}, ${F}`}
          title=${`Segment ${b}`}
        >
          <span class="cell-num">${b}</span>
        </div>
      `)}return m`
      <div class="strip-scroll">
        <div
          class="strip"
          style="grid-template-columns: repeat(${B}, 1fr)"
          tabindex="0"
          role="listbox"
          aria-multiselectable="true"
          aria-activedescendant=${o(this._cursor)}
          aria-label=${`Segment painter, ${B} segments`}
          @pointerdown=${this._onDown}
          @keydown=${this._onKey}
        >
          ${n}
        </div>
      </div>
    `}_renderGradient(){return m`
      <section>
        ${this._renderStopEditor()}
        <div class="row heading">
          <span class="label">Gradient preview</span>
        </div>
        <canvas class="preview" height="44"></canvas>
        <div class="row controls">
          <button class="btn primary" @click=${this._applyGradient}>
            Apply gradient
          </button>
        </div>
      </section>
    `}_renderStopEditor(){let r=this._activeStops(),w=r.length,u=`linear-gradient(90deg, ${r.map((o,n)=>`${o} ${n/(w-1)*100}%`).join(", ")})`;return m`
      <div class="row heading">
        <span class="label">Gradient stops</span>
        <span class="hint">${w} of ${gr} to ${Gr}</span>
      </div>
      <div class="gradient-track">
        <div class="gradient-bar" style="background:${u}">
          ${r.map((o,n)=>m`
              <div
                class="handle ${this._dragStop===n?"dragging":""}"
                style="left:${this._dragStop===n&&this._dragFrac!==null?this._dragFrac*100:n/(w-1)*100}%;background:${o}"
                @pointerdown=${(b)=>this._startStopDrag(b,n)}
                title=${`Stop ${n+1}`}
              ></div>
            `)}
        </div>
      </div>
      <div class="stops">
        ${r.map((o,n)=>m`
            <div class="stop">
              <input
                type="color"
                aria-label=${`Stop ${n+1} colour`}
                .value=${o}
                @input=${(b)=>this._recolourStop(n,b.target.value)}
              />
              <button
                class="btn tiny"
                ?disabled=${n===0}
                @click=${()=>this._moveStop(n,-1)}
                aria-label=${`Move stop ${n+1} left`}
              >
                ←
              </button>
              <button
                class="btn tiny"
                ?disabled=${n===w-1}
                @click=${()=>this._moveStop(n,1)}
                aria-label=${`Move stop ${n+1} right`}
              >
                →
              </button>
              <button
                class="btn tiny"
                ?disabled=${w<=gr}
                @click=${()=>this._removeStop(n)}
                aria-label=${`Remove stop ${n+1}`}
                title="Remove stop"
              >
                &times;
              </button>
            </div>
          `)}
        <button
          class="btn tiny add"
          ?disabled=${w>=Gr}
          @click=${this._addStop}
          aria-label="Add stop"
          title="Add stop"
        >
          +
        </button>
      </div>
    `}_renderPresets(){return m`
      <section>
        <div class="row heading">
          <span class="label">Presets</span>
        </div>
        <div class="row presets">
          ${Jw.map((r)=>m`
              <button
                class="preset"
                @click=${()=>this._applyPreset(r)}
                title=${r.name}
                aria-label=${r.name}
              >
                <span
                  class="swatch"
                  style="background:${this._presetSwatch(r.stops)}"
                ></span>
                <span class="preset-name">${r.name}</span>
              </button>
            `)}
        </div>
      </section>
    `}_renderSaveCurrent(){return m`
      <section>
        <div class="row heading">
          <span class="label">Save current</span>
        </div>
        <div class="row controls">
          <input
            class="effect-name"
            type="text"
            aria-label="New effect name"
            placeholder="Name this look"
            .value=${this._effectName}
            @input=${(r)=>this._effectName=r.target.value}
            @keydown=${(r)=>this._onSaveKey(r,()=>void this._saveCurrent())}
          />
          <button
            class="btn primary"
            ?disabled=${this._effectName.trim()===""}
            @click=${this._saveCurrent}
          >
            Save current as effect
          </button>
        </div>
        <p class="help">Snapshots the strip's current colours as a named effect.</p>
      </section>
    `}_renderStudio(){let r=this._availableKindDescriptors();return m`
      <div id="panel-studio" role="tabpanel" aria-labelledby="tab-studio">
        ${this._renderScopeBand("draft")}
        <section>
          <div class="row heading">
            <span class="label">Effect kind</span>
          </div>
          <div class="kinds" role="radiogroup" aria-label="Effect kind" @keydown=${this._onKindKey}>
            ${r.map((w)=>m`
                <button
                  class="kind ${this._studioKind===w.id?"active":""}"
                  role="radio"
                  aria-checked=${this._studioKind===w.id?"true":"false"}
                  tabindex=${this._studioKind===w.id?"0":"-1"}
                  ?disabled=${this._editingId!==null&&this._studioKind!==w.id}
                  @click=${()=>this._selectKind(w.id)}
                >
                  ${w.label}
                </button>
              `)}
          </div>
          ${Zw.length>0?m`
                <div class="kinds-soon">
                  <span>Coming next:</span>
                  ${Zw.map((w)=>m`
                      <button class="kind soon" disabled aria-disabled="true">
                        ${w.label}<span class="soon-tag">soon</span>
                      </button>
                    `)}
                </div>
              `:q}
        </section>
        ${this._studioKind==="static"?this._renderStaticEditor():this._studioKind==="gradient"?this._renderGradientAuthor():this._studioKind==="sketch"?this._renderSketchAuthor():this._studioKind==="flat"?this._renderFlatAuthor():this._studioKind==="combo"?this._renderComboAuthor():this._renderPendingAuthor()}
      </div>
    `}_renderStaticEditor(){let r=this._staticColors.filter((u)=>u!==null).length,w=jw(this._staticColors.map((u)=>u===null?null:a(u)),this._staticBrightness);return m`
      <section>
        <div class="row heading">
          <span class="label">Static segments</span>
          <span class="hint">${r} painted · ${this._selection.size} selected</span>
        </div>
        ${this._renderStrip(this._staticColors,"unchanged")}
        <div class="row controls">
          <input
            type="color"
            aria-label="Paint colour"
            .value=${this._paintColor}
            @input=${(u)=>this._paintColor=u.target.value}
          />
          <button class="btn primary" @click=${this._paintStatic}>Paint selected</button>
          <button class="btn" @click=${this._setUnchangedStatic}>Clear selected</button>
          <button class="btn" @click=${this._selectAll}>Select all</button>
          <button class="btn" @click=${this._resetStatic}>Reset</button>
        </div>
        <p class="help">
          Paint a colour onto chosen segments; hatched segments are left as they are on the strip.
        </p>
        ${this._renderStudioSave(w,"Paint at least one segment to save.")}
      </section>
    `}_renderSketchAuthor(){let r=this._sketchColors.filter((o)=>o!==null).length,w=Yr(this._sketchColors.map((o)=>o===null?null:a(o)),this._sketchMotion,this._sketchSpeed,this._sketchBrightness,a(this._sketchBackground)),u=$w(w).map(j);return m`
      <section>
        <div class="row heading">
          <span class="label">Sketch foreground</span>
          <span class="hint">${r} painted · ${this._selection.size} selected</span>
        </div>
        ${this._renderStrip(this._sketchColors,"background",this._sketchBackground)}
        <div class="row controls">
          <label class="colour-control">
            <span>Foreground</span>
            <input
              type="color"
              aria-label="Sketch foreground colour"
              .value=${this._paintColor}
              @input=${(o)=>this._paintColor=o.target.value}
            />
          </label>
          <label class="colour-control">
            <span>Background</span>
            <input
              type="color"
              aria-label="Sketch background colour"
              .value=${this._sketchBackground}
              @input=${(o)=>this._sketchBackground=o.target.value}
            />
          </label>
          <button class="btn primary" @click=${this._paintSketch}>Paint selected</button>
          <button class="btn" @click=${this._clearSketchSelection}>Use background</button>
          <button class="btn" @click=${this._selectAll}>Select all</button>
          <button class="btn" @click=${this._resetSketch}>Reset</button>
        </div>
        <p class="help">
          Hatched cells use the background; solid cells are the animated foreground palette.
        </p>
      </section>
      <section>
        <div class="row heading">
          <span class="label">Motion</span>
        </div>
        <div
          class="motion-grid"
          role="radiogroup"
          aria-label="Sketch motion"
          @keydown=${this._onMotionKey}
        >
          ${rr.map((o)=>m`
              <button
                class="motion ${this._sketchMotion===o.code?"active":""}"
                role="radio"
                aria-checked=${this._sketchMotion===o.code?"true":"false"}
                tabindex=${this._sketchMotion===o.code?"0":"-1"}
                @click=${()=>this._sketchMotion=o.code}
              >
                ${o.label}
              </button>
            `)}
        </div>
        <label class="range-row">
          <span>Speed</span>
          <input
            type="range"
            min="0"
            max="100"
            .value=${String(this._sketchSpeed)}
            aria-label=${`Sketch speed, ${this._sketchSpeed} percent`}
            @input=${(o)=>this._sketchSpeed=Number(o.target.value)}
          />
          <output>${this._sketchSpeed}%</output>
        </label>
        <label class="range-row">
          <span>Brightness</span>
          <input
            type="range"
            min="0"
            max="100"
            .value=${String(this._sketchBrightness)}
            aria-label=${`Sketch brightness, ${this._sketchBrightness} percent`}
            @input=${(o)=>this._sketchBrightness=Number(o.target.value)}
          />
          <output>${this._sketchBrightness}%</output>
        </label>
      </section>
      <section>
        <div class="row heading">
          <span class="label">Representative preview</span>
          <span class="preview-badge">Approximate · animated on device</span>
        </div>
        ${this._renderPreviewStrip(u)}
        ${this._renderStudioSave(!0,"")}
      </section>
    `}_renderPaletteEditor(r,w,u,o,n,b,$){return m`
      <div class="row heading">
        <span class="label">${u}</span>
        <span class="hint">${r.length} of ${w}</span>
      </div>
      <div class="palette-editor">
        ${r.map((E,p)=>m`
            <div class="palette-chip">
              <span class="palette-number">${p+1}</span>
              <input
                type="color"
                aria-label=${`${u} colour ${p+1}`}
                .value=${E}
                @input=${(F)=>o(p,F.target.value)}
              />
              <button
                class="btn tiny"
                ?disabled=${p===0}
                @click=${()=>$(p,-1)}
                aria-label=${`Move colour ${p+1} left`}
              >
                ←
              </button>
              <button
                class="btn tiny"
                ?disabled=${p===r.length-1}
                @click=${()=>$(p,1)}
                aria-label=${`Move colour ${p+1} right`}
              >
                →
              </button>
              <button
                class="btn tiny danger"
                ?disabled=${r.length<=1}
                @click=${()=>b(p)}
                aria-label=${`Remove colour ${p+1}`}
              >
                ×
              </button>
            </div>
          `)}
        <button
          class="btn palette-add"
          ?disabled=${r.length>=w}
          @click=${n}
        >
          Add colour
        </button>
      </div>
    `}_renderFlatAuthor(){let r=D(this._flatFamily),w=this._flatPalette.length===0?[]:Array.from({length:B},(u,o)=>this._flatPalette[o%this._flatPalette.length]);return m`
      <section>
        <div class="row heading">
          <span class="label">Animation family</span>
          <span class="hint">Human-labelled catalogue</span>
        </div>
        <div
          class="family-grid"
          role="radiogroup"
          aria-label="Flat animation family"
          @keydown=${this._onFlatFamilyKey}
        >
          ${C.map((u)=>m`
              <button
                class="family ${u.family===this._flatFamily?"active":""}"
                role="radio"
                aria-checked=${u.family===this._flatFamily?"true":"false"}
                tabindex=${u.family===this._flatFamily?"0":"-1"}
                @click=${()=>this._selectFlatFamily(u.family)}
              >
                ${u.label}
              </button>
            `)}
        </div>
        <div class="row heading">
          <span class="label">Variant</span>
          <span class="hint">Up to ${r.palette_max} colours</span>
        </div>
        <div
          class="variant-grid"
          role="radiogroup"
          aria-label=${`${r.label} variant`}
          @keydown=${this._onFlatVariantKey}
        >
          ${r.variants.map((u)=>m`
              <button
                class="variant ${u.variant===this._flatVariant?"active":""}"
                role="radio"
                aria-checked=${u.variant===this._flatVariant?"true":"false"}
                tabindex=${u.variant===this._flatVariant?"0":"-1"}
                @click=${()=>this._flatVariant=u.variant}
              >
                ${u.label}
              </button>
            `)}
        </div>
        <p class="help">${r.description}</p>
      </section>
      <section>
        ${this._renderPaletteEditor(this._flatPalette,r.palette_max,"Shared palette order",(u,o)=>this._setFlatPaletteColour(u,o),()=>this._addFlatPaletteColour(),(u)=>this._removeFlatPaletteColour(u),(u,o)=>this._moveFlatPaletteColour(u,o))}
        ${w.length>0?m`
              <div class="row heading">
                <span class="label">Representative preview</span>
                <span class="preview-badge">Approximate · animated on device</span>
              </div>
              ${this._renderPreviewStrip(w)}
            `:m`<p class="help">Add at least one colour to preview and save this effect.</p>`}
      </section>
      <section>
        <label class="range-row">
          <span>${r.control_label}</span>
          <input
            type="range"
            min="0"
            max="100"
            .value=${String(this._flatSpeed)}
            aria-label=${`${r.control_label}, ${this._flatSpeed} percent`}
            @input=${(u)=>this._flatSpeed=Number(u.target.value)}
          />
          <output>${this._flatSpeed}%</output>
        </label>
        <button class="btn" @click=${this._resetFlat}>Reset Flat draft</button>
        ${this._renderStudioSave(this._flatPalette.length>0,"Add at least one palette colour to save.")}
      </section>
    `}_renderComboAuthor(){let r=this._comboPalette.length===0?[]:Array.from({length:B},(w,u)=>this._comboPalette[u%this._comboPalette.length]);return m`
      <section>
        <div class="row heading">
          <span class="label">Effect chain</span>
          <span class="hint">${this._comboEffects.length} of 4 steps</span>
        </div>
        ${this._comboEffects.length===0?m`<p class="help">Add at least one Flat effect to the chain.</p>`:m`
              <ol class="combo-chain">
                ${this._comboEffects.map((w,u)=>{let o=wr(w.family);return m`
                    <li class="combo-step">
                      <span class="combo-number">${u+1}</span>
                      <label>
                        <span class="sr-only">Step ${u+1} family</span>
                        <select
                          aria-label=${`Step ${u+1} family`}
                          .value=${String(w.family)}
                          @change=${(n)=>this._setComboFamily(u,Number(n.target.value))}
                        >
                          ${P.map((n)=>m`
                              <option value=${String(n.family)}>${n.label}</option>
                            `)}
                        </select>
                      </label>
                      <label>
                        <span class="sr-only">Step ${u+1} variant</span>
                        <select
                          aria-label=${`Step ${u+1} variant`}
                          .value=${String(w.variant)}
                          @change=${(n)=>this._setComboVariant(u,Number(n.target.value))}
                        >
                          ${o.variants.map((n)=>m`
                              <option value=${String(n.variant)}>${n.label}</option>
                            `)}
                        </select>
                      </label>
                      <div class="combo-actions">
                        <button
                          class="btn tiny"
                          ?disabled=${u===0}
                          @click=${()=>this._moveComboStep(u,-1)}
                          aria-label=${`Move step ${u+1} up`}
                        >
                          ↑
                        </button>
                        <button
                          class="btn tiny"
                          ?disabled=${u===this._comboEffects.length-1}
                          @click=${()=>this._moveComboStep(u,1)}
                          aria-label=${`Move step ${u+1} down`}
                        >
                          ↓
                        </button>
                        <button
                          class="btn tiny danger"
                          ?disabled=${this._comboEffects.length<=1}
                          @click=${()=>this._removeComboStep(u)}
                          aria-label=${`Remove step ${u+1}`}
                        >
                          ×
                        </button>
                      </div>
                    </li>
                  `})}
              </ol>
            `}
        <button
          class="btn"
          ?disabled=${this._comboEffects.length>=4}
          @click=${this._addComboStep}
        >
          Add step
        </button>
      </section>
      <section>
        ${this._renderPaletteEditor(this._comboPalette,8,"Shared palette order",(w,u)=>this._setComboPaletteColour(w,u),()=>this._addComboPaletteColour(),(w)=>this._removeComboPaletteColour(w),(w,u)=>this._moveComboPaletteColour(w,u))}
        ${r.length>0?m`
              <div class="row heading">
                <span class="label">Sequence preview</span>
                <span class="preview-badge">Approximate · animated on device</span>
              </div>
              ${this._renderPreviewStrip(r)}
            `:m`<p class="help">Add at least one shared palette colour.</p>`}
      </section>
      <section>
        <label class="range-row">
          <span>Speed</span>
          <input
            type="range"
            min="0"
            max="100"
            .value=${String(this._comboSpeed)}
            aria-label=${`Combo speed, ${this._comboSpeed} percent`}
            @input=${(w)=>this._comboSpeed=Number(w.target.value)}
          />
          <output>${this._comboSpeed}%</output>
        </label>
        <button class="btn" @click=${this._resetCombo}>Reset Combo draft</button>
        ${this._renderStudioSave(this._comboEffects.length>0&&this._comboPalette.length>0,this._comboEffects.length===0?"Add at least one effect step to save.":"Add at least one shared palette colour to save.")}
      </section>
    `}_renderPendingAuthor(){let r=I.find((u)=>u.id===this._studioKind)?.label??this._studioKind,w=this._loadedContent?.kind===this._studioKind;return m`
      <section class="pending-author">
        <div class="row heading">
          <span class="label">${r}</span>
          <span class="hint">Editor coming next</span>
        </div>
        <p class="help">
          ${w?`This ${r} effect is loaded safely, but this editor is not available in the current build.`:`The ${r} editor will be enabled in the next Studio phase.`}
        </p>
        ${this._editingId!==null?m`<button class="btn" @click=${this._cancelEdit}>Cancel edit</button>`:q}
      </section>
    `}_renderGradientAuthor(){let r=nr(this._studioStops.map(a),B).map(j);return m`
      <section>
        ${this._renderStopEditor()}
        <div class="row heading">
          <span class="label">Draft preview · ${B} segments</span>
        </div>
        ${this._renderPreviewStrip(r)}
        <p class="help">Saves the colour stops as a gradient effect.</p>
        ${this._renderStudioSave(!0,"")}
      </section>
    `}_renderPreviewStrip(r){return m`
      <div class="strip-scroll">
        <div
          class="strip preview-strip"
          style="grid-template-columns: repeat(${B}, 1fr)"
          aria-hidden="true"
        >
          ${r.map((w,u)=>m`
              <div class="cell" style="background:${w}" title=${`Segment ${u+1}`}>
                <span class="cell-num">${u+1}</span>
              </div>
            `)}
        </div>
      </div>
    `}_renderStudioSave(r,w){let u=this._studioName.trim()!=="",o=this._editingId!==null;return m`
      ${o?m`<div class="edit-band" role="status">
            <span>Editing a saved effect. Update keeps its stable ID and effect kind.</span>
            <button class="btn" @click=${this._cancelEdit}>Cancel edit</button>
          </div>`:q}
      <div class="row controls">
        <input
          class="effect-name"
          type="text"
          aria-label="Effect name"
          placeholder="Name this effect"
          .value=${this._studioName}
          @input=${(n)=>this._studioName=n.target.value}
          @keydown=${(n)=>this._onSaveKey(n,()=>void this._saveStudio())}
        />
        <button
          class="btn primary"
          ?disabled=${!u||!r}
          @click=${this._saveStudio}
        >
          ${o?"Update effect":"Save effect"}
        </button>
      </div>
      ${!r&&w!==""?m`<p class="help">${w}</p>`:q}
    `}_renderLibrary(r){let w=br(r.attributes?.custom_effects),u=br(r.attributes?.quarantined_custom_effects),o=[...w,...u],n=typeof r.attributes?.effect==="string"?r.attributes.effect:null;return m`
      <div id="panel-library" role="tabpanel" aria-labelledby="tab-library">
        <section>
          <div class="row heading">
            <span class="label">Saved effects</span>
            <span class="hint">${w.length} available</span>
          </div>
          ${w.length===0?m`<p class="help">
                No custom effects saved yet. Create one in the Studio tab, or snapshot the strip from
                the Now tab.
              </p>`:m`
                <p class="help">Select an effect to apply it.</p>
                <ul class="effects" role="list">
                  ${w.map((b)=>this._renderEffectRow(b,n,o))}
                </ul>
              `}
        </section>
        ${u.length===0?q:m`
              <section>
                <div class="row heading">
                  <span class="label">Unavailable on this model</span>
                  <span class="hint">${u.length} preserved</span>
                </div>
                <p class="help">
                  These effects are kept for export or deletion, but cannot be applied or edited on
                  this light.
                </p>
                <ul class="effects" role="list">
                  ${u.map((b)=>this._renderQuarantinedEffectRow(b))}
                </ul>
              </section>
            `}
        <section>
          <details class="import-panel">
            <summary>Import effect JSON</summary>
            <div class="import-body">
              <textarea
                class="import-json"
                aria-label="Effect JSON"
                placeholder="Paste an exported Govee effect here"
                .value=${this._importText}
                @input=${(b)=>this._importText=b.target.value}
              ></textarea>
              <input
                class="import-file"
                type="file"
                accept=".json,application/json"
                @change=${this._loadImportFile}
              />
              <div class="row controls">
                <button class="btn" @click=${this._chooseImportFile}>Load JSON file</button>
                <button
                  class="btn primary"
                  ?disabled=${this._importText.trim()===""}
                  @click=${()=>this._reviewImport(o)}
                >
                  Review import
                </button>
                <button
                  class="btn"
                  ?disabled=${this._importText===""}
                  @click=${()=>this._importText=""}
                >
                  Clear
                </button>
              </div>
              <p class="help">
                Import opens an untrusted file as a Studio draft. Nothing is saved until you review it.
              </p>
            </div>
          </details>
        </section>
      </div>
    `}_renderEffectRow(r,w,u){if(this._renamingId===r.id)return m`
        <li class="effect renaming">
          <input
            class="effect-name rename-input"
            type="text"
            aria-label=${`New name for ${r.name}`}
            .value=${this._renameValue}
            @input=${(b)=>this._renameValue=b.target.value}
            @keydown=${(b)=>this._onRenameKey(b,r)}
          />
          <button class="btn primary" @click=${()=>this._commitRename(r)}>
            Save
          </button>
          <button class="btn" @click=${this._cancelRename}>Cancel</button>
        </li>
      `;if(this._deletingId===r.id)return m`
        <li class="effect">
          <span class="confirm-text">Delete "${r.name}"?</span>
          <button
            class="btn confirm-cancel"
            @click=${this._cancelDelete}
            @keydown=${this._onDeleteKey}
          >
            Cancel
          </button>
          <button
            class="btn danger primary"
            @click=${()=>this._deleteEffect(r)}
            @keydown=${this._onDeleteKey}
          >
            Delete
          </button>
        </li>
      `;let o=w!==null&&w===r.name,n=this._busyKey?.endsWith(`:${r.id}`)??!1;return m`
      <li class="effect ${o?"active":""}">
        <div class="effect-main">
          ${o?m`<span class="badge-active" aria-current="true">✓ Active</span>`:m`<button
                class="btn primary"
                @click=${()=>this._applyEffect(r)}
                aria-label=${`Apply ${r.name}`}
              >
                Apply
              </button>`}
          <span class="effect-label" title=${r.name}>${r.name}</span>
        </div>
        <div class="effect-actions">
          <button
            class="btn"
            ?disabled=${n}
            @click=${()=>void this._editEffect(r)}
            aria-label=${`Edit ${r.name}`}
          >
            Edit
          </button>
          <button
            class="btn"
            ?disabled=${n}
            @click=${()=>void this._duplicateEffect(r,u)}
            aria-label=${`Duplicate ${r.name}`}
          >
            Duplicate
          </button>
          <details class="effect-more">
            <summary class="btn">More</summary>
            <div class="more-actions">
              <button
                class="btn"
                ?disabled=${n}
                @click=${()=>void this._exportEffect(r)}
                aria-label=${`Export ${r.name}`}
              >
                ${n?"Working…":"Export"}
              </button>
              <button
                class="btn"
                @click=${()=>this._startRename(r)}
                aria-label=${`Rename ${r.name}`}
              >
                Rename
              </button>
              <button
                class="btn danger"
                @click=${()=>this._askDelete(r)}
                aria-label=${`Delete ${r.name}`}
              >
                Delete
              </button>
            </div>
          </details>
        </div>
      </li>
    `}_renderQuarantinedEffectRow(r){if(this._deletingId===r.id)return m`
        <li class="effect quarantined">
          <span class="confirm-text">Delete "${r.name}"?</span>
          <button class="btn confirm-cancel" @click=${this._cancelDelete}>Cancel</button>
          <button class="btn danger primary" @click=${()=>this._deleteEffect(r)}>
            Delete
          </button>
        </li>
      `;let w=this._busyKey?.endsWith(`:${r.id}`)??!1;return m`
      <li class="effect quarantined">
        <div class="effect-main">
          <span class="badge-unavailable">Unavailable</span>
          <span class="effect-label" title=${r.name}>${r.name}</span>
        </div>
        <div class="effect-actions">
          <button
            class="btn"
            ?disabled=${w}
            @click=${()=>void this._exportEffect(r)}
            aria-label=${`Export ${r.name}`}
          >
            ${w?"Working…":"Export"}
          </button>
          <button
            class="btn danger"
            @click=${()=>this._askDelete(r)}
            aria-label=${`Delete ${r.name}`}
          >
            Delete
          </button>
        </div>
      </li>
    `}static styles=cr}customElements.define("govee-led-ble-card",Qw);window.customCards=window.customCards||[];window.customCards.push({type:"govee-led-ble-card",name:"Govee LED BLE",description:"Paint, compose and save custom effects for a segment-capable Govee LED BLE light.",preview:!1});console.info("%c govee-led-ble-card ","background:#1982c4;color:#fff;border-radius:3px","loaded");
