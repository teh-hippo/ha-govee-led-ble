var i=globalThis,pr=i.ShadowRoot&&(i.ShadyCSS===void 0||i.ShadyCSS.nativeShadow)&&"adoptedStyleSheets"in Document.prototype&&"replace"in CSSStyleSheet.prototype,$r=Symbol(),Cr=new WeakMap;class mr{constructor(r,u,w){if(this._$cssResult$=!0,w!==$r)throw Error("CSSResult is not constructable. Use `unsafeCSS` or `css` instead.");this.cssText=r,this.t=u}get styleSheet(){let r=this.i,u=this.t;if(pr&&r===void 0){let w=u!==void 0&&u.length===1;w&&(r=Cr.get(u)),r===void 0&&((this.i=r=new CSSStyleSheet).replaceSync(this.cssText),w&&Cr.set(u,r))}return r}toString(){return this.cssText}}var Zu=(r)=>new mr(typeof r=="string"?r:r+"",void 0,$r),s=(r,...u)=>{let w=r.length===1?r[0]:u.reduce((o,n,b)=>o+((p)=>{if(p._$cssResult$===!0)return p.cssText;if(typeof p=="number")return p;throw Error("Value passed to 'css' function must be a 'css' function result: "+p+". Use 'unsafeCSS' to pass non-literal values, but take care to ensure page security.")})(n)+r[b+1],r[0]);return new mr(w,r,$r)},Qu=(r,u)=>{if(pr)r.adoptedStyleSheets=u.map((w)=>w instanceof CSSStyleSheet?w:w.styleSheet);else for(let w of u){let o=document.createElement("style"),n=i.litNonce;n!==void 0&&o.setAttribute("nonce",n),o.textContent=w.cssText,r.appendChild(o)}},Xr=pr?(r)=>r:(r)=>r instanceof CSSStyleSheet?((u)=>{let w="";for(let o of u.cssRules)w+=o.cssText;return Zu(w)})(r):r,{is:Du,defineProperty:Vu,getOwnPropertyDescriptor:Fu,getOwnPropertyNames:Wu,getOwnPropertySymbols:Cu,getPrototypeOf:Xu}=Object,e=globalThis,gr=e.trustedTypes,gu=gr?gr.emptyScript:"",Gu=e.reactiveElementPolyfillSupport,O=(r,u)=>r,br={toAttribute(r,u){switch(u){case Boolean:r=r?gu:null;break;case Object:case Array:r=r==null?r:JSON.stringify(r)}return r},fromAttribute(r,u){let w=r;switch(u){case Boolean:w=r!==null;break;case Number:w=r===null?null:Number(r);break;case Object:case Array:try{w=JSON.parse(r)}catch(o){w=null}}return w}},lr=(r,u)=>!Du(r,u),Gr={attribute:!0,type:String,converter:br,reflect:!1,useDefault:!1,hasChanged:lr};Symbol.metadata??=Symbol("metadata"),e.litPropertyMetadata??=new WeakMap;class _ extends HTMLElement{static addInitializer(r){this.o(),(this.l??=[]).push(r)}static get observedAttributes(){return this.finalize(),this.u&&[...this.u.keys()]}static createProperty(r,u=Gr){if(u.state&&(u.attribute=!1),this.o(),this.prototype.hasOwnProperty(r)&&((u=Object.create(u)).wrapped=!0),this.elementProperties.set(r,u),!u.noAccessor){let w=Symbol(),o=this.getPropertyDescriptor(r,w,u);o!==void 0&&Vu(this.prototype,r,o)}}static getPropertyDescriptor(r,u,w){let{get:o,set:n}=Fu(this.prototype,r)??{get(){return this[u]},set(b){this[u]=b}};return{get:o,set(b){let p=o?.call(this);n?.call(this,b),this.requestUpdate(r,p,w)},configurable:!0,enumerable:!0}}static getPropertyOptions(r){return this.elementProperties.get(r)??Gr}static o(){if(this.hasOwnProperty(O("elementProperties")))return;let r=Xu(this);r.finalize(),r.l!==void 0&&(this.l=[...r.l]),this.elementProperties=new Map(r.elementProperties)}static finalize(){if(this.hasOwnProperty(O("finalized")))return;if(this.finalized=!0,this.o(),this.hasOwnProperty(O("properties"))){let u=this.properties,w=[...Wu(u),...Cu(u)];for(let o of w)this.createProperty(o,u[o])}let r=this[Symbol.metadata];if(r!==null){let u=litPropertyMetadata.get(r);if(u!==void 0)for(let[w,o]of u)this.elementProperties.set(w,o)}this.u=new Map;for(let[u,w]of this.elementProperties){let o=this.p(u,w);o!==void 0&&this.u.set(o,u)}this.elementStyles=this.finalizeStyles(this.styles)}static finalizeStyles(r){let u=[];if(Array.isArray(r)){let w=new Set(r.flat(1/0).reverse());for(let o of w)u.unshift(Xr(o))}else r!==void 0&&u.push(Xr(r));return u}static p(r,u){let w=u.attribute;return w===!1?void 0:typeof w=="string"?w:typeof r=="string"?r.toLowerCase():void 0}constructor(){super(),this.v=void 0,this.isUpdatePending=!1,this.hasUpdated=!1,this.m=null,this._()}_(){this.S=new Promise((r)=>this.enableUpdating=r),this._$AL=new Map,this.$(),this.requestUpdate(),this.constructor.l?.forEach((r)=>r(this))}addController(r){(this.P??=new Set).add(r),this.renderRoot!==void 0&&this.isConnected&&r.hostConnected?.()}removeController(r){this.P?.delete(r)}$(){let r=new Map,u=this.constructor.elementProperties;for(let w of u.keys())this.hasOwnProperty(w)&&(r.set(w,this[w]),delete this[w]);r.size>0&&(this.v=r)}createRenderRoot(){let r=this.shadowRoot??this.attachShadow(this.constructor.shadowRootOptions);return Qu(r,this.constructor.elementStyles),r}connectedCallback(){this.renderRoot??=this.createRenderRoot(),this.enableUpdating(!0),this.P?.forEach((r)=>r.hostConnected?.())}enableUpdating(r){}disconnectedCallback(){this.P?.forEach((r)=>r.hostDisconnected?.())}attributeChangedCallback(r,u,w){this._$AK(r,w)}C(r,u){let w=this.constructor.elementProperties.get(r),o=this.constructor.p(r,w);if(o!==void 0&&w.reflect===!0){let n=(w.converter?.toAttribute!==void 0?w.converter:br).toAttribute(u,w.type);this.m=r,n==null?this.removeAttribute(o):this.setAttribute(o,n),this.m=null}}_$AK(r,u){let w=this.constructor,o=w.u.get(r);if(o!==void 0&&this.m!==o){let n=w.getPropertyOptions(o),b=typeof n.converter=="function"?{fromAttribute:n.converter}:n.converter?.fromAttribute!==void 0?n.converter:br;this.m=o;let p=b.fromAttribute(u,n.type);this[o]=p??this.T?.get(o)??p,this.m=null}}requestUpdate(r,u,w,o=!1,n){if(r!==void 0){let b=this.constructor;if(o===!1&&(n=this[r]),w??=b.getPropertyOptions(r),!((w.hasChanged??lr)(n,u)||w.useDefault&&w.reflect&&n===this.T?.get(r)&&!this.hasAttribute(b.p(r,w))))return;this.M(r,u,w)}this.isUpdatePending===!1&&(this.S=this.k())}M(r,u,{useDefault:w,reflect:o,wrapped:n},b){w&&!(this.T??=new Map).has(r)&&(this.T.set(r,b??u??this[r]),n!==!0||b!==void 0)||(this._$AL.has(r)||(this.hasUpdated||w||(u=void 0),this._$AL.set(r,u)),o===!0&&this.m!==r&&(this.A??=new Set).add(r))}async k(){this.isUpdatePending=!0;try{await this.S}catch(u){Promise.reject(u)}let r=this.scheduleUpdate();return r!=null&&await r,!this.isUpdatePending}scheduleUpdate(){return this.performUpdate()}performUpdate(){if(!this.isUpdatePending)return;if(!this.hasUpdated){if(this.renderRoot??=this.createRenderRoot(),this.v){for(let[o,n]of this.v)this[o]=n;this.v=void 0}let w=this.constructor.elementProperties;if(w.size>0)for(let[o,n]of w){let{wrapped:b}=n,p=this[o];b!==!0||this._$AL.has(o)||p===void 0||this.M(o,void 0,n,p)}}let r=!1,u=this._$AL;try{r=this.shouldUpdate(u),r?(this.willUpdate(u),this.P?.forEach((w)=>w.hostUpdate?.()),this.update(u)):this.U()}catch(w){throw r=!1,this.U(),w}r&&this._$AE(u)}willUpdate(r){}_$AE(r){this.P?.forEach((u)=>u.hostUpdated?.()),this.hasUpdated||(this.hasUpdated=!0,this.firstUpdated(r)),this.updated(r)}U(){this._$AL=new Map,this.isUpdatePending=!1}get updateComplete(){return this.getUpdateComplete()}getUpdateComplete(){return this.S}shouldUpdate(r){return!0}update(r){this.A&&=this.A.forEach((u)=>this.C(u,this[u])),this.U()}updated(r){}firstUpdated(r){}}_.elementStyles=[],_.shadowRootOptions={mode:"open"},_[O("elementProperties")]=new Map,_[O("finalized")]=new Map,Gu?.({ReactiveElement:_}),(e.reactiveElementVersions??=[]).push("2.1.2");var kr=globalThis,_r=(r)=>r,x=kr.trustedTypes,Hr=x?x.createPolicy("lit-html",{createHTML:(r)=>r}):void 0,fr="$lit$",W=`lit$${Math.random().toFixed(9).slice(2)}$`,Ur="?"+W,_u=`<${Ur}>`,P=document,A=()=>P.createComment(""),N=(r)=>r===null||typeof r!="object"&&typeof r!="function",Er=Array.isArray,Hu=(r)=>Er(r)||typeof r?.[Symbol.iterator]=="function",nr=`[ 	
\f\r]`,I=/<(?:(!--|\/[^a-zA-Z])|(\/?[a-zA-Z][^>\s]*)|(\/?$))/g,Pr=/-->/g,hr=/>/g,G=RegExp(`>|${nr}(?:([^\\s"'>=/]+)(${nr}*=${nr}*(?:[^ 	
\f\r"'\`<>=]|("|')|))|$)`,"g"),Kr=/'/g,Lr=/"/g,yr=/^(?:script|style|textarea|title)$/i,qr=(r)=>(u,...w)=>({_$litType$:r,strings:u,values:w}),$=qr(1),Au=qr(2),Nu=qr(3),K=Symbol.for("lit-noChange"),q=Symbol.for("lit-nothing"),Mr=new WeakMap,H=P.createTreeWalker(P,129);function Ir(r,u){if(!Er(r)||!r.hasOwnProperty("raw"))throw Error("invalid template strings array");return Hr!==void 0?Hr.createHTML(u):u}var Pu=(r,u)=>{let w=r.length-1,o=[],n,b=u===2?"<svg>":u===3?"<math>":"",p=I;for(let k=0;k<w;k++){let m=r[k],B,E,R=-1,j=0;for(;j<m.length&&(p.lastIndex=j,E=p.exec(m),E!==null);)j=p.lastIndex,p===I?E[1]==="!--"?p=Pr:E[1]!==void 0?p=hr:E[2]!==void 0?(yr.test(E[2])&&(n=RegExp("</"+E[2],"g")),p=G):E[3]!==void 0&&(p=G):p===G?E[0]===">"?(p=n??I,R=-1):E[1]===void 0?R=-2:(R=p.lastIndex-E[2].length,B=E[1],p=E[3]===void 0?G:E[3]==='"'?Lr:Kr):p===Lr||p===Kr?p=G:p===Pr||p===hr?p=I:(p=G,n=void 0);let g=p===G&&r[k+1].startsWith("/>")?" ":"";b+=p===I?m+_u:R>=0?(o.push(B),m.slice(0,R)+fr+m.slice(R)+W+g):m+W+(R===-2?k:g)}return[Ir(r,b+(r[w]||"<?>")+(u===2?"</svg>":u===3?"</math>":"")),o]};class S{constructor({strings:r,_$litType$:u},w){let o;this.parts=[];let n=0,b=0,p=r.length-1,k=this.parts,[m,B]=Pu(r,u);if(this.el=S.createElement(m,w),H.currentNode=this.el.content,u===2||u===3){let E=this.el.content.firstChild;E.replaceWith(...E.childNodes)}for(;(o=H.nextNode())!==null&&k.length<p;){if(o.nodeType===1){if(o.hasAttributes())for(let E of o.getAttributeNames())if(E.endsWith(fr)){let R=B[b++],j=o.getAttribute(E).split(W),g=/([.?@])?(.*)/.exec(R);k.push({type:1,index:n,name:g[2],strings:j,ctor:g[1]==="."?Ar:g[1]==="?"?Nr:g[1]==="@"?Sr:v}),o.removeAttribute(E)}else E.startsWith(W)&&(k.push({type:6,index:n}),o.removeAttribute(E));if(yr.test(o.tagName)){let E=o.textContent.split(W),R=E.length-1;if(R>0){o.textContent=x?x.emptyScript:"";for(let j=0;j<R;j++)o.append(E[j],A()),H.nextNode(),k.push({type:2,index:++n});o.append(E[R],A())}}}else if(o.nodeType===8)if(o.data===Ur)k.push({type:2,index:n});else{let E=-1;for(;(E=o.data.indexOf(W,E+1))!==-1;)k.push({type:7,index:n}),E+=W.length-1}n++}}static createElement(r,u){let w=P.createElement("template");return w.innerHTML=r,w}}function L(r,u,w=r,o){if(u===K)return u;let n=o!==void 0?w.N?.[o]:w.O,b=N(u)?void 0:u._$litDirective$;return n?.constructor!==b&&(n?._$AO?.(!1),b===void 0?n=void 0:(n=new b(r),n._$AT(r,w,o)),o!==void 0?(w.N??=[])[o]=n:w.O=n),n!==void 0&&(u=L(r,n._$AS(r,u.values),n,o)),u}class Or{constructor(r,u){this._$AV=[],this._$AN=void 0,this._$AD=r,this._$AM=u}get parentNode(){return this._$AM.parentNode}get _$AU(){return this._$AM._$AU}R(r){let{el:{content:u},parts:w}=this._$AD,o=(r?.creationScope??P).importNode(u,!0);H.currentNode=o;let n=H.nextNode(),b=0,p=0,k=w[0];for(;k!==void 0;){if(b===k.index){let m;k.type===2?m=new d(n,n.nextSibling,this,r):k.type===1?m=new k.ctor(n,k.name,k.strings,this,r):k.type===6&&(m=new dr(n,this,r)),this._$AV.push(m),k=w[++p]}b!==k?.index&&(n=H.nextNode(),b++)}return H.currentNode=P,o}V(r){let u=0;for(let w of this._$AV)w!==void 0&&(w.strings!==void 0?(w._$AI(r,w,u),u+=w.strings.length-2):w._$AI(r[u])),u++}}class d{get _$AU(){return this._$AM?._$AU??this.D}constructor(r,u,w,o){this.type=2,this._$AH=q,this._$AN=void 0,this._$AA=r,this._$AB=u,this._$AM=w,this.options=o,this.D=o?.isConnected??!0}get parentNode(){let r=this._$AA.parentNode,u=this._$AM;return u!==void 0&&r?.nodeType===11&&(r=u.parentNode),r}get startNode(){return this._$AA}get endNode(){return this._$AB}_$AI(r,u=this){r=L(this,r,u),N(r)?r===q||r==null||r===""?(this._$AH!==q&&this._$AR(),this._$AH=q):r!==this._$AH&&r!==K&&this.L(r):r._$litType$!==void 0?this.j(r):r.nodeType!==void 0?this.I(r):Hu(r)?this.H(r):this.L(r)}B(r){return this._$AA.parentNode.insertBefore(r,this._$AB)}I(r){this._$AH!==r&&(this._$AR(),this._$AH=this.B(r))}L(r){this._$AH!==q&&N(this._$AH)?this._$AA.nextSibling.data=r:this.I(P.createTextNode(r)),this._$AH=r}j(r){let{values:u,_$litType$:w}=r,o=typeof w=="number"?this._$AC(r):(w.el===void 0&&(w.el=S.createElement(Ir(w.h,w.h[0]),this.options)),w);if(this._$AH?._$AD===o)this._$AH.V(u);else{let n=new Or(o,this),b=n.R(this.options);n.V(u),this.I(b),this._$AH=n}}_$AC(r){let u=Mr.get(r.strings);return u===void 0&&Mr.set(r.strings,u=new S(r)),u}H(r){Er(this._$AH)||(this._$AH=[],this._$AR());let u=this._$AH,w,o=0;for(let n of r)o===u.length?u.push(w=new d(this.B(A()),this.B(A()),this,this.options)):w=u[o],w._$AI(n),o++;o<u.length&&(this._$AR(w&&w._$AB.nextSibling,o),u.length=o)}_$AR(r=this._$AA.nextSibling,u){for(this._$AP?.(!1,!0,u);r!==this._$AB;){let w=_r(r).nextSibling;_r(r).remove(),r=w}}setConnected(r){this._$AM===void 0&&(this.D=r,this._$AP?.(r))}}class v{get tagName(){return this.element.tagName}get _$AU(){return this._$AM._$AU}constructor(r,u,w,o,n){this.type=1,this._$AH=q,this._$AN=void 0,this.element=r,this.name=u,this._$AM=o,this.options=n,w.length>2||w[0]!==""||w[1]!==""?(this._$AH=Array(w.length-1).fill(new String),this.strings=w):this._$AH=q}_$AI(r,u=this,w,o){let n=this.strings,b=!1;if(n===void 0)r=L(this,r,u,0),b=!N(r)||r!==this._$AH&&r!==K,b&&(this._$AH=r);else{let p=r,k,m;for(r=n[0],k=0;k<n.length-1;k++)m=L(this,p[w+k],u,k),m===K&&(m=this._$AH[k]),b||=!N(m)||m!==this._$AH[k],m===q?r=q:r!==q&&(r+=(m??"")+n[k+1]),this._$AH[k]=m}b&&!o&&this.W(r)}W(r){r===q?this.element.removeAttribute(this.name):this.element.setAttribute(this.name,r??"")}}class Ar extends v{constructor(){super(...arguments),this.type=3}W(r){this.element[this.name]=r===q?void 0:r}}class Nr extends v{constructor(){super(...arguments),this.type=4}W(r){this.element.toggleAttribute(this.name,!!r&&r!==q)}}class Sr extends v{constructor(r,u,w,o,n){super(r,u,w,o,n),this.type=5}_$AI(r,u=this){if((r=L(this,r,u,0)??q)===K)return;let w=this._$AH,o=r===q&&w!==q||r.capture!==w.capture||r.once!==w.once||r.passive!==w.passive,n=r!==q&&(w===q||o);o&&this.element.removeEventListener(this.name,this,w),n&&this.element.addEventListener(this.name,this,r),this._$AH=r}handleEvent(r){typeof this._$AH=="function"?this._$AH.call(this.options?.host??this.element,r):this._$AH.handleEvent(r)}}class dr{constructor(r,u,w){this.element=r,this.type=6,this._$AN=void 0,this._$AM=u,this.options=w}get _$AU(){return this._$AM._$AU}_$AI(r){L(this,r)}}var hu=kr.litHtmlPolyfillSupport;hu?.(S,d),(kr.litHtmlVersions??=[]).push("3.3.3");var Ku=(r,u,w)=>{let o=w?.renderBefore??u,n=o._$litPart$;if(n===void 0){let b=w?.renderBefore??null;o._$litPart$=n=new d(u.insertBefore(A(),b),b,void 0,w??{})}return n._$AI(r),n},Jr=globalThis;class V extends _{constructor(){super(...arguments),this.renderOptions={host:this},this.rt=void 0}createRenderRoot(){let r=super.createRenderRoot();return this.renderOptions.renderBefore??=r.firstChild,r}update(r){let u=this.render();this.hasUpdated||(this.renderOptions.isConnected=this.isConnected),super.update(r),this.rt=Ku(u,this.renderRoot,this.renderOptions)}connectedCallback(){super.connectedCallback(),this.rt?.setConnected(!0)}disconnectedCallback(){super.disconnectedCallback(),this.rt?.setConnected(!1)}render(){return K}}V._$litElement$=!0,V.finalized=!0,Jr.litElementHydrateSupport?.({LitElement:V});var Lu=Jr.litElementPolyfillSupport;Lu?.({LitElement:V});(Jr.litElementVersions??=[]).push("4.2.2");var vr=s`
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
`;class cr extends V{static properties={hass:{attribute:!1},_config:{state:!0}};setConfig(r){this._config={...r}}render(){return $`
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
    `}_entityChanged(r){let u=r.detail?.value??"",w={...this._config,entity:u};this.dispatchEvent(new CustomEvent("config-changed",{detail:{config:w},bubbles:!0,composed:!0}))}static styles=s`
    .editor {
      padding: 8px;
    }
    .help {
      margin: 8px 0 0;
      color: var(--secondary-text-color);
      font-size: 0.85em;
    }
  `}customElements.define("govee-led-ble-card-editor",cr);var Tr=[{id:"fade",label:"Fade",family:0,palette_max:8,control_label:"Speed",description:"Uses a Govee Fade pattern with the shared palette.",variants:[{id:"fade-1",label:"Fade 1",variant:0},{id:"fade-2",label:"Fade 2",variant:1},{id:"fade-3",label:"Fade 3",variant:2}]},{id:"jumping",label:"Jumping",family:1,palette_max:8,control_label:"Speed",description:"Uses a Govee Jumping pattern with the shared palette.",variants:[{id:"jumping-1",label:"Jumping 1",variant:0},{id:"jumping-2",label:"Jumping 2",variant:2}]},{id:"twinkle",label:"Twinkle",family:2,palette_max:8,control_label:"Speed",description:"Uses a Govee Twinkle pattern with the shared palette.",variants:[{id:"twinkle-1",label:"Twinkle 1",variant:0},{id:"twinkle-2",label:"Twinkle 2",variant:1},{id:"twinkle-3",label:"Twinkle 3",variant:2}]},{id:"marquee",label:"Marquee",family:3,palette_max:8,control_label:"Speed",description:"Uses a Govee Marquee pattern with the shared palette.",variants:[{id:"marquee-1",label:"Marquee 1",variant:3},{id:"marquee-2",label:"Marquee 2",variant:4},{id:"marquee-3",label:"Marquee 3",variant:5}]},{id:"music",label:"Music",family:4,palette_max:8,control_label:"Sensitivity",description:"Uses a Govee DIY Music pattern, separate from the light's Music mode.",variants:[{id:"music-1",label:"Music 1",variant:8},{id:"music-2",label:"Music 2",variant:6},{id:"music-3",label:"Music 3",variant:7}]},{id:"chasing",label:"Chasing",family:8,palette_max:8,control_label:"Speed",description:"Uses a Govee Chasing pattern with the shared palette.",variants:[{id:"chasing-1",label:"Chasing 1",variant:9},{id:"chasing-2",label:"Chasing 2",variant:10}]},{id:"rainbow",label:"Rainbow",family:9,palette_max:8,control_label:"Speed",description:"Uses a Govee Rainbow pattern with the shared palette.",variants:[{id:"rainbow-1",label:"Rainbow 1",variant:9},{id:"rainbow-2",label:"Rainbow 2",variant:10}]},{id:"crossing",label:"Crossing",family:10,palette_max:3,control_label:"Speed",description:"Uses the single Govee Crossing pattern with up to three colours.",variants:[{id:"crossing",label:"Crossing",variant:0}]}];var z=Tr,t=[{code:2,label:"Cycle"},{code:9,label:"Clockwise"},{code:10,label:"Counter-clockwise"},{code:15,label:"Twinkle"},{code:19,label:"Gradient"},{code:20,label:"Breathe"}];function C(r,u){if(r===null||typeof r!=="object"||Array.isArray(r))throw Error(`${u} must be an object.`);return r}function M(r,u){if(typeof r!=="string"||r.trim()==="")throw Error(`${u} must be a non-empty string.`);return r.trim()}function F(r,u){if(typeof r!=="number"||!Number.isInteger(r))throw Error(`${u} must be an integer.`);return r}function c(r,u){let w=F(r,u);if(w<0||w>100)throw Error(`${u} must be from 0 to 100.`);return w}function lu(r,u){let w=F(r,u);if(w<0||w>255)throw Error(`${u} must be from 0 to 255.`);return w}function l(r,u){if(!Array.isArray(r))throw Error(`${u} must be an array.`);return r}function Rr(r,u){let w=l(r,u);if(w.length!==3||w.some((o)=>typeof o!=="number"||!Number.isInteger(o)||o<0||o>255))throw Error(`${u} must contain three channels from 0 to 255.`);return[w[0],w[1],w[2]]}function fu(r,u){return r===null?null:Rr(r,u)}function Br(r,u){return l(r,u).map((w,o)=>Rr(w,`${u}[${o}]`))}function ir(r,u){return l(r,u).map((w,o)=>fu(w,`${u}[${o}]`))}function xr(r){let u=C(r,"Effect content"),w=M(u.kind,"Effect kind");switch(w){case"segments":{let o=u.brightness,n=null;if(o!==null)n=l(o,"Segment brightness").map((b,p)=>b===null?null:c(b,`Segment brightness[${p}]`));return{kind:w,colors:ir(u.colors,"Segment colours"),brightness:n}}case"vibrant":{let o=Br(u.stops,"Gradient stops");if(o.length<2||o.length>5)throw Error("Gradient stops must contain from 2 to 5 colours.");return{kind:w,stops:o}}case"sketch":{let o=F(u.motion,"Sketch motion");if(!t.some((n)=>n.code===o))throw Error("Sketch motion is not supported.");return{kind:w,motion:o,speed:c(u.speed,"Sketch speed"),brightness:c(u.brightness,"Sketch brightness"),background:Rr(u.background,"Sketch background"),colors:ir(u.colors,"Sketch colours")}}case"flat":{let o=F(u.family,"Flat family"),n=F(u.variant,"Flat variant");f(o,n);let b=Br(u.palette,"Flat palette"),p=Y(o);if(b.length>p.palette_max)throw Error(`${p.label} accepts up to ${p.palette_max} colours.`);return{kind:w,family:o,variant:n,speed:c(u.speed,"Flat speed"),palette:b}}case"combo":{let o=l(u.effects,"Combo effects").map((b,p)=>{let k=l(b,`Combo effects[${p}]`);if(k.length!==2)throw Error(`Combo effects[${p}] must contain a family and variant.`);let m=F(k[0],`Combo effects[${p}].family`),B=F(k[1],`Combo effects[${p}].variant`);return f(m,B),[m,B]});if(o.length>4)throw Error("Combo accepts up to four steps.");let n=Br(u.palette,"Combo palette");if(n.length>8)throw Error("Combo accepts up to 8 colours.");return{kind:w,variant:lu(u.variant,"Combo variant"),speed:c(u.speed,"Combo speed"),palette:n,effects:o}}default:throw Error(`Unsupported effect kind "${w}".`)}}function sr(r){let u=C(r,"Export response"),w=F(u.segment_count,"Export segment count");if(w<=0)throw Error("Export segment count must be positive.");return{id:M(u.id,"Effect ID"),name:M(u.name,"Effect name"),model:M(u.model,"Effect model"),segment_count:w,content:C(u.content,"Effect content")}}function Uu(r){let u=sr(r);return{...u,content:xr(u.content)}}function ar(r,u){let w=C(r,"Entity service response");if(!(u in w))throw Error(`The export response did not include ${u}.`);return Uu(w[u])}function er(r,u){let w=C(r,"Entity service response");if(!(u in w))throw Error(`The export response did not include ${u}.`);return sr(w[u])}function tr(r){return{schema_version:1,integration:"ha_govee_led_ble",source:{model:r.model,segment_count:r.segment_count},effect:{name:r.name,content:r.content}}}function ru(r,u){let w;try{w=JSON.parse(r)}catch{throw Error("This is not valid JSON.")}let o=C(w,"Effect document");if(o.schema_version!==1)throw Error("This effect uses an unsupported schema version.");if(o.integration!=="ha_govee_led_ble")throw Error("This file is not a Govee LED BLE effect.");let n=C(o.source,"Effect source"),b=M(n.model,"Source model"),p=F(n.segment_count,"Source segment count");if(p<=0)throw Error("Source segment count must be positive.");if(p!==u.segmentCount)throw Error(`This effect needs ${p} segments; this light has ${u.segmentCount}.`);if(u.model!==null&&u.model!==b)throw Error(`This effect was exported for ${b}; this light is ${u.model}.`);let k=C(o.effect,"Effect"),m=xr(k.content);if((m.kind==="segments"||m.kind==="sketch")&&m.colors.length>p)throw Error(`This effect contains more than ${p} segments.`);if(m.kind==="segments"&&m.brightness!==null&&m.brightness.length>p)throw Error(`This effect contains more than ${p} brightness values.`);return{schema_version:1,integration:"ha_govee_led_ble",source:{model:b,segment_count:p},effect:{name:M(k.name,"Effect name"),content:m}}}function uu(r){switch(r.kind){case"segments":return"static";case"vibrant":return"gradient";default:return r.kind}}function zr(r,u,w,o,n){return{kind:"sketch",motion:u,speed:w,brightness:o,background:[n[0],n[1],n[2]],colors:r.map((b)=>b===null?null:[b[0],b[1],b[2]])}}function Y(r){let u=z.find((w)=>w.family===r);if(u===void 0)throw Error(`Unknown Flat family ${r}.`);return u}function wu(r,u,w,o){let n=Y(r);if(!n.variants.some((b)=>b.variant===u))throw Error(`Unknown variant for ${n.label}.`);if(o.length===0)throw Error("Add at least one palette colour.");if(o.length>n.palette_max)throw Error(`${n.label} accepts up to ${n.palette_max} colours.`);return{kind:"flat",family:r,variant:u,speed:w,palette:o.map((b)=>[b[0],b[1],b[2]])}}function f(r,u){let w=Y(r),o=w.variants.find((n)=>n.variant===u);if(o===void 0)throw Error(`Unknown variant for ${w.label}.`);return o.label}function ou(r,u,w,o=0){if(!Number.isInteger(o)||o<0||o>255)throw Error("Combo variant must be from 0 to 255.");if(r.length===0)throw Error("Add at least one Combo step.");if(r.length>4)throw Error("Combo accepts up to four steps.");for(let[n,b]of r)f(n,b);if(w.length===0)throw Error("Add at least one palette colour.");if(w.length>8)throw Error("Combo accepts up to 8 colours.");return{kind:"combo",variant:o,speed:u,palette:w.map((n)=>[n[0],n[1],n[2]]),effects:r.map(([n,b])=>[n,b])}}function nu(r){let u=Math.max(0,Math.min(100,r.brightness))/100;return r.colors.map((w)=>{return(w??r.background).map((n)=>Math.round(n*u))})}function jr(r,u){let w=new Set(u.map(T)),o=`${bu(r)} copy`;if(!w.has(T(o)))return o;for(let n=2;;n+=1){let b=`${o} ${n}`;if(!w.has(T(b)))return b}}function bu(r){return r.trim().replace(/^["'“”‘’]+|["'“”‘’]+$/gu,"").trim().replace(/\s+/gu," ")}function T(r){return bu(r).toLocaleLowerCase().replaceAll("ß","ss").replaceAll("ς","σ")}function pu(r,u){let w=r.trim();return u.some((n)=>T(n)===T(w))?jr(w,u):w}function $u(r){return`${r.trim().toLocaleLowerCase().replace(/[^a-z0-9]+/g,"-").replace(/^-+|-+$/g,"")||"govee-effect"}.json`}var J=15;function D(r,u,w){return Math.max(u,Math.min(w,r))}function a(r){let u=r.replace("#","");return[parseInt(u.slice(0,2),16),parseInt(u.slice(2,4),16),parseInt(u.slice(4,6),16)]}function Z(r){return"#"+r.map((u)=>D(Math.round(u),0,255).toString(16).padStart(2,"0")).join("")}function rr(r,u){if(r.length===0)throw Error("no stops");if(r.length===1){let m=r[0];return[m[0],m[1],m[2]]}let w=r.length-1,o=D(u,0,1)*w,n=D(Math.floor(o),0,w-1),b=o-n,p=r[n],k=r[n+1];return[p[0]+(k[0]-p[0])*b,p[1]+(k[1]-p[1])*b,p[2]+(k[2]-p[2])*b]}function yu(r){let u=Math.floor(r),w=r-u;if(w<0.5)return u;if(w>0.5)return u+1;return u%2===0?u:u+1}function ur(r,u=15){if(r.length===0)throw Error("no stops");if(u<=0)return[];if(r.length===1){let w=r[0];return Array.from({length:u},()=>[w[0],w[1],w[2]])}return Array.from({length:u},(w,o)=>{let n=u>1?o/(u-1):0;return rr(r,n).map(yu)})}function Zr(r){let u=new Map,w=[];return r.forEach((o,n)=>{let b=`${o[0]},${o[1]},${o[2]}`,p=u.get(b);if(p===void 0)p={segments:[],rgb_color:[o[0],o[1],o[2]]},u.set(b,p),w.push(p);p.segments.push(n+1)}),w}var mu=[{id:"sunset",name:"Sunset",stops:[[255,89,94],[255,146,76],[255,202,58]]},{id:"ocean",name:"Ocean",stops:[[15,32,89],[25,130,196],[112,193,179]]},{id:"forest",name:"Forest",stops:[[27,67,50],[45,106,79],[149,213,178]]},{id:"rainbow",name:"Rainbow",stops:[[255,0,0],[255,183,0],[0,200,83],[0,145,234],[170,0,255]]},{id:"warm-white",name:"Warm white",stops:[[255,183,107]]},{id:"cool-white",name:"Cool white",stops:[[188,220,255]]}];function ku(r,u=15){return Zr(ur(r.stops,u))}function Eu(r){return[...new Set(r)].sort((u,w)=>u-w)}function qu(r,u){let w=Math.min(r,u),o=Math.max(r,u),n=new Set;for(let b=w;b<=o;b++)n.add(b);return n}function Qr(r,u){let w=new Set(r);if(w.has(u))w.delete(u);else w.add(u);return w}function Ju(r=15){let u=new Set;for(let w=1;w<=r;w++)u.add(w);return u}function X(){return new Set}function Dr(r){if(r===null||typeof r!=="object"||Array.isArray(r))return[];let u=[];for(let[w,o]of Object.entries(r)){if(typeof o!=="string")continue;let n=o.trim();if(n==="")continue;u.push({id:w,name:n})}return u.sort((w,o)=>{let n=w.name.toLowerCase(),b=o.name.toLowerCase();if(n!==b)return n<b?-1:1;if(w.id!==o.id)return w.id<o.id?-1:1;return 0}),u}var U=[{id:"now",label:"Now"},{id:"studio",label:"Studio"},{id:"library",label:"Library"}];function y(r,u,w){if(w<=0)return r;switch(u){case"ArrowRight":case"ArrowDown":return(r+1)%w;case"ArrowLeft":case"ArrowUp":return(r-1+w)%w;case"Home":return 0;case"End":return w-1;default:return r}}var wr=[{id:"static",label:"Static",available:!0},{id:"gradient",label:"Gradient",available:!0},{id:"sketch",label:"Sketch",available:!0},{id:"flat",label:"Flat",available:!0},{id:"combo",label:"Combo",available:!0}];function Bu(r,u=null){let w=u!==null&&u.some((o)=>o!==null);return{kind:"segments",colors:r.map((o)=>o===null?null:[o[0],o[1],o[2]]),brightness:w?u.map((o)=>o===null?null:o):null}}function Ru(r,u=null){return r.some((w)=>w!==null)||u!==null&&u.some((w)=>w!==null)}function au(r){return{kind:"vibrant",stops:r.map((u)=>[u[0],u[1],u[2]])}}function Yr(r){if(r!==null&&typeof r==="object"){let u=r.message;if(typeof u==="string"&&u.trim()!=="")return u}return null}function Q(r,u="Something went wrong."){if(typeof r==="string"&&r.trim()!=="")return r;let w=Yr(r);if(w!==null)return w;if(r!==null&&typeof r==="object"){let o=r,n=Yr(o.error)??Yr(o.body);if(n!==null)return n}return u}var h=["#ff595e","#ffca3a","#1982c4"],Vr="#33cc66",Fr=2,Wr=5,zu="Govee Effect Studio",or=wr.filter((r)=>r.available),ju=wr.filter((r)=>!r.available);function Iu(r){if(!Array.isArray(r))return null;let u=[];for(let w of r){if(!Array.isArray(w)||w.length<3)return null;let[o,n,b]=w;if(typeof o!=="number"||typeof n!=="number"||typeof b!=="number")return null;u.push([o,n,b])}return u}function Ou(r,u){let w=window.document.createElement("a");return w.download=r,w.href=u,w}class Yu extends V{static properties={hass:{attribute:!1},_config:{state:!0},_tab:{state:!0},_studioKind:{state:!0},_selection:{state:!0},_cursor:{state:!0},_paintColor:{state:!0},_staticColors:{state:!0},_staticBrightness:{state:!0},_sketchColors:{state:!0},_sketchMotion:{state:!0},_sketchSpeed:{state:!0},_sketchBrightness:{state:!0},_sketchBackground:{state:!0},_flatFamily:{state:!0},_flatVariant:{state:!0},_flatSpeed:{state:!0},_flatPalette:{state:!0},_comboEffects:{state:!0},_comboVariant:{state:!0},_comboSpeed:{state:!0},_comboPalette:{state:!0},_stops:{state:!0},_studioStops:{state:!0},_dragStop:{state:!0},_dragFrac:{state:!0},_effectName:{state:!0},_studioName:{state:!0},_editingId:{state:!0},_loadedContent:{state:!0},_pendingDraft:{state:!0},_importText:{state:!0},_busyKey:{state:!0},_renamingId:{state:!0},_renameValue:{state:!0},_deletingId:{state:!0},_feedback:{state:!0}};_dragging=!1;_dragAnchor=1;_touchStart=null;_ro;_draftBaseline="";_editingOriginalName=null;_editingOriginalContent=null;constructor(){super();this._tab="now",this._studioKind="static",this._selection=new Set,this._cursor=1,this._paintColor=Vr,this._staticColors=Array.from({length:J},()=>null),this._staticBrightness=null,this._sketchColors=Array.from({length:J},()=>null),this._sketchMotion=9,this._sketchSpeed=51,this._sketchBrightness=100,this._sketchBackground="#000000",this._flatFamily=z[0].family,this._flatVariant=z[0].variants[0].variant,this._flatSpeed=50,this._flatPalette=[...h],this._comboEffects=[{family:z[0].family,variant:z[0].variants[0].variant}],this._comboVariant=0,this._comboSpeed=50,this._comboPalette=[...h],this._stops=[...h],this._studioStops=[...h],this._dragStop=null,this._dragFrac=null,this._effectName="",this._studioName="",this._editingId=null,this._loadedContent=null,this._pendingDraft=null,this._importText="",this._busyKey=null,this._renamingId=null,this._renameValue="",this._deletingId=null,this._feedback=null,this._draftBaseline=this._draftSignature()}static getStubConfig(r){return{entity:(r?Object.keys(r.states).find((w)=>w.startsWith("light.")&&Array.isArray(r.states[w].attributes?.segment_colors)):void 0)??""}}static getConfigElement(){return document.createElement("govee-led-ble-card-editor")}setConfig(r){if(!r)throw Error("Invalid configuration");this._config={...r}}getCardSize(){return 12}connectedCallback(){super.connectedCallback(),this._ro=new ResizeObserver(()=>{this._updateClipped(),this._drawNowPreview()}),this._ro.observe(this)}disconnectedCallback(){super.disconnectedCallback(),this._ro?.disconnect(),window.removeEventListener("pointermove",this._onMove),window.removeEventListener("pointerup",this._onUp),window.removeEventListener("pointercancel",this._onUp),window.removeEventListener("pointerup",this._onTouchUp),window.removeEventListener("pointercancel",this._onTouchCancel),window.removeEventListener("pointermove",this._onStopMove),window.removeEventListener("pointerup",this._onStopUp)}updated(){this._reconcileDraftIds(),this._updateClipped(),this._drawNowPreview()}_reconcileDraftIds(){let r=this._config?.entity,u=r?this.hass?.states[r]:void 0;if(!u)return;let w=Dr(u.attributes?.custom_effects),o=new Set(w.map((n)=>n.id));if(this._editingId!==null){let n=w.find((b)=>b.id===this._editingId);if(n===void 0)this._editingId=null,this._editingOriginalName=null,this._editingOriginalContent=null,this._draftBaseline="",this._feedback={kind:"info",text:"The saved effect was removed elsewhere. Its Studio draft is now a new effect."};else if(this._editingOriginalName!==null&&this._studioName.trim()===this._editingOriginalName&&n.name!==this._editingOriginalName){let b=this._currentContentSignature()===this._editingOriginalContent;if(this._studioName=n.name,this._editingOriginalName=n.name,b)this._draftBaseline=this._draftSignature()}}if(this._pendingDraft?.editingId!==null&&this._pendingDraft?.editingId!==void 0&&!o.has(this._pendingDraft.editingId))this._pendingDraft={...this._pendingDraft,editingId:null,feedback:"The saved effect was removed elsewhere. Its loaded content will open as a new draft."}}_updateClipped(){for(let r of this.renderRoot.querySelectorAll(".strip-scroll"))r.classList.toggle("clipped",r.scrollWidth>r.clientWidth+1)}_selectTab(r){if(this._tab===r)return;this._tab=r,this._selection=X(),this._cursor=1}_onTabKey(r){let u=U.findIndex((o)=>o.id===this._tab),w=y(u,r.key,U.length);if(w===u)return;r.preventDefault(),this._selectTab(U[w].id),this.updateComplete.then(()=>{this.renderRoot.querySelector(`#tab-${U[w].id}`)?.focus()})}_draftSignature(){let r={kind:this._studioKind,name:this._studioName};switch(this._studioKind){case"static":return JSON.stringify({...r,colors:this._staticColors,brightness:this._staticBrightness});case"gradient":return JSON.stringify({...r,stops:this._studioStops});case"sketch":return JSON.stringify({...r,colors:this._sketchColors,motion:this._sketchMotion,speed:this._sketchSpeed,brightness:this._sketchBrightness,background:this._sketchBackground});case"flat":return JSON.stringify({...r,family:this._flatFamily,variant:this._flatVariant,speed:this._flatSpeed,palette:this._flatPalette});case"combo":return JSON.stringify({...r,effects:this._comboEffects,variant:this._comboVariant,speed:this._comboSpeed,palette:this._comboPalette})}}_hasUnsavedDraft(){return this._draftSignature()!==this._draftBaseline}_selectKind(r){if(this._editingId!==null&&r!==this._studioKind)return;let u=this._hasUnsavedDraft();if(this._studioKind=r,this._loadedContent=null,!u&&this._editingId===null)this._draftBaseline=this._draftSignature()}_onKindKey(r){if(this._editingId!==null)return;let u=or.findIndex((o)=>o.id===this._studioKind),w=y(u,r.key,or.length);if(w===u)return;r.preventDefault(),this._selectKind(or[w].id),this.updateComplete.then(()=>{this.renderRoot.querySelector('.kinds .kind[aria-checked="true"]')?.focus()})}_focusChecked(r){this.updateComplete.then(()=>{this.renderRoot.querySelector(`${r}[aria-checked="true"]`)?.focus()})}_onMotionKey(r){let u=t.map((n)=>n.code),w=u.indexOf(this._sketchMotion),o=y(w,r.key,u.length);if(o===w)return;r.preventDefault(),this._sketchMotion=u[o],this._focusChecked(".motion")}_onFlatFamilyKey(r){let u=z.map((n)=>n.family),w=u.indexOf(this._flatFamily),o=y(w,r.key,u.length);if(o===w)return;r.preventDefault(),this._selectFlatFamily(u[o]),this._focusChecked(".family")}_onFlatVariantKey(r){let u=Y(this._flatFamily).variants.map((n)=>n.variant),w=u.indexOf(this._flatVariant),o=y(w,r.key,u.length);if(o===w)return;r.preventDefault(),this._flatVariant=u[o],this._focusChecked(".variant")}_segmentColors(){let r=this._config?.entity;if(!r||!this.hass)return null;let u=this.hass.states[r];if(!u)return null;return Iu(u.attributes?.segment_colors)}_cellFromClientX(r){let u=this.renderRoot.querySelector(".strip");if(!u)return 1;let w=u.getBoundingClientRect(),o=w.width/J;return D(Math.floor((r-w.left)/o),0,J-1)+1}_onDown(r){if(r.pointerType==="touch"){this._touchStart={x:r.clientX,y:r.clientY,cell:this._cellFromClientX(r.clientX)},window.addEventListener("pointerup",this._onTouchUp),window.addEventListener("pointercancel",this._onTouchCancel);return}r.preventDefault(),this._dragging=!0,this._dragAnchor=this._cellFromClientX(r.clientX),this._cursor=this._dragAnchor,this._selection=new Set([this._dragAnchor]),this.renderRoot.querySelector(".strip")?.focus(),window.addEventListener("pointermove",this._onMove),window.addEventListener("pointerup",this._onUp),window.addEventListener("pointercancel",this._onUp)}_onMove=(r)=>{if(!this._dragging)return;let u=this._cellFromClientX(r.clientX);this._selection=qu(this._dragAnchor,u),this._cursor=u};_onUp=()=>{this._dragging=!1,window.removeEventListener("pointermove",this._onMove),window.removeEventListener("pointerup",this._onUp),window.removeEventListener("pointercancel",this._onUp)};_onTouchUp=(r)=>{let u=this._touchStart;if(this._clearTouchGesture(),u===null||Math.hypot(r.clientX-u.x,r.clientY-u.y)>10)return;this._cursor=u.cell,this._selection=Qr(this._selection,u.cell)};_onTouchCancel=()=>{this._clearTouchGesture()};_clearTouchGesture(){this._touchStart=null,window.removeEventListener("pointerup",this._onTouchUp),window.removeEventListener("pointercancel",this._onTouchCancel)}_onKey(r){let u=r.key,w=["ArrowRight","ArrowDown","ArrowLeft","ArrowUp","Home","End"];if(u==="ArrowRight"||u==="ArrowDown")this._cursor=D(this._cursor+1,1,J),r.preventDefault();else if(u==="ArrowLeft"||u==="ArrowUp")this._cursor=D(this._cursor-1,1,J),r.preventDefault();else if(u==="Home")this._cursor=1,r.preventDefault();else if(u==="End")this._cursor=J,r.preventDefault();else if(u===" "||u==="Spacebar")this._selection=Qr(this._selection,this._cursor),r.preventDefault();else if(u==="Enter"){if(this._tab==="studio")this._paintActiveDraft();else this._applyPaint();r.preventDefault()}else if(u==="Escape")this._dragging=!1,this._selection=X(),r.preventDefault();if(w.includes(u))this._scrollCursorIntoView()}_scrollCursorIntoView(){this.updateComplete.then(()=>{this.renderRoot.querySelector(".cell.cursor")?.scrollIntoView({inline:"nearest",block:"nearest"})})}_selectAll(){this._selection=Ju(J)}_clear(){this._selection=X()}_applyPaint(){let r=this._config?.entity;if(!this.hass||!r||this._selection.size===0)return;let u=[{segments:Eu(this._selection),rgb_color:a(this._paintColor)}];this.hass.callService("ha_govee_led_ble","paint_segments",{groups:u},{entity_id:r})}_paintStatic(){if(this._selection.size===0)return;let r=[...this._staticColors];for(let u of this._selection)r[u-1]=this._paintColor;this._staticColors=r}_paintSketch(){if(this._selection.size===0)return;let r=[...this._sketchColors];for(let u of this._selection)r[u-1]=this._paintColor;this._sketchColors=r}_paintActiveDraft(){if(this._studioKind==="sketch")this._paintSketch();else this._paintStatic()}_setUnchangedStatic(){if(this._selection.size===0)return;let r=[...this._staticColors];for(let u of this._selection)r[u-1]=null;this._staticColors=r}_clearSketchSelection(){if(this._selection.size===0)return;let r=[...this._sketchColors];for(let u of this._selection)r[u-1]=null;this._sketchColors=r}_resetStatic(){this._staticColors=Array.from({length:J},()=>null),this._staticBrightness=null,this._selection=X(),this._finishDraftReset()}_resetSketch(){this._sketchColors=Array.from({length:J},()=>null),this._sketchMotion=9,this._sketchSpeed=51,this._sketchBrightness=100,this._sketchBackground="#000000",this._selection=X(),this._finishDraftReset()}_selectFlatFamily(r){let u=Y(r);if(this._flatPalette.length>u.palette_max){this._feedback={kind:"error",text:`${u.label} accepts up to ${u.palette_max} colours. Remove some first.`};return}this._flatFamily=r,this._flatVariant=u.variants[0].variant,this._feedback=null}_setFlatPaletteColour(r,u){let w=[...this._flatPalette];w[r]=u,this._flatPalette=w}_addFlatPaletteColour(){let r=Y(this._flatFamily).palette_max;if(this._flatPalette.length>=r)return;this._flatPalette=[...this._flatPalette,Vr]}_removeFlatPaletteColour(r){this._flatPalette=this._flatPalette.filter((u,w)=>w!==r)}_moveFlatPaletteColour(r,u){let w=r+u;if(w<0||w>=this._flatPalette.length)return;let o=[...this._flatPalette];[o[r],o[w]]=[o[w],o[r]],this._flatPalette=o}_resetFlat(){this._flatFamily=z[0].family,this._flatVariant=z[0].variants[0].variant,this._flatSpeed=50,this._flatPalette=[...h],this._finishDraftReset()}_setComboFamily(r,u){let w=Y(u);this._comboEffects=this._comboEffects.map((o,n)=>n===r?{family:u,variant:w.variants[0].variant}:o)}_setComboVariant(r,u){let w=this._comboEffects[r];f(w.family,u),this._comboEffects=this._comboEffects.map((o,n)=>n===r?{...o,variant:u}:o)}_addComboStep(){if(this._comboEffects.length>=4)return;let r=z[0];this._comboEffects=[...this._comboEffects,{family:r.family,variant:r.variants[0].variant}]}_removeComboStep(r){this._comboEffects=this._comboEffects.filter((u,w)=>w!==r)}_moveComboStep(r,u){let w=r+u;if(w<0||w>=this._comboEffects.length)return;let o=[...this._comboEffects];[o[r],o[w]]=[o[w],o[r]],this._comboEffects=o}_setComboPaletteColour(r,u){let w=[...this._comboPalette];w[r]=u,this._comboPalette=w}_addComboPaletteColour(){if(this._comboPalette.length>=8)return;this._comboPalette=[...this._comboPalette,Vr]}_removeComboPaletteColour(r){this._comboPalette=this._comboPalette.filter((u,w)=>w!==r)}_moveComboPaletteColour(r,u){let w=r+u;if(w<0||w>=this._comboPalette.length)return;let o=[...this._comboPalette];[o[r],o[w]]=[o[w],o[r]],this._comboPalette=o}_resetCombo(){let r=z[0];this._comboEffects=[{family:r.family,variant:r.variants[0].variant}],this._comboVariant=0,this._comboSpeed=50,this._comboPalette=[...h],this._finishDraftReset()}_finishDraftReset(){if(this._editingId===null)this._draftBaseline=this._draftSignature()}_activeStops(){return this._tab==="studio"?this._studioStops:this._stops}_setActiveStops(r){if(this._tab==="studio")this._studioStops=r;else this._stops=r}_addStop(){let r=this._activeStops();if(r.length>=Wr)return;let u=rr(r.map(a),0.5);this._setActiveStops([...r,Z(u)])}_removeStop(r){let u=this._activeStops();if(u.length<=Fr)return;this._setActiveStops(u.filter((w,o)=>o!==r))}_moveStop(r,u){let w=r+u,o=this._activeStops();if(w<0||w>=o.length)return;let n=[...o];[n[r],n[w]]=[n[w],n[r]],this._setActiveStops(n)}_recolourStop(r,u){let w=[...this._activeStops()];w[r]=u,this._setActiveStops(w)}_stopTargetIndex(r){let u=this.renderRoot.querySelector(".gradient-bar"),w=this._activeStops();if(!u)return this._dragStop??0;let o=u.getBoundingClientRect(),n=D((r-o.left)/o.width,0,1);return D(Math.round(n*(w.length-1)),0,w.length-1)}_startStopDrag(r,u){r.preventDefault(),this._dragStop=u,window.addEventListener("pointermove",this._onStopMove),window.addEventListener("pointerup",this._onStopUp)}_onStopMove=(r)=>{if(this._dragStop===null)return;let u=this.renderRoot.querySelector(".gradient-bar");if(!u)return;let w=u.getBoundingClientRect();this._dragFrac=D((r.clientX-w.left)/w.width,0,1)};_onStopUp=(r)=>{if(this._dragStop===null)return;let u=this._dragStop,w=this._stopTargetIndex(r.clientX);if(u!==w){let o=[...this._activeStops()],[n]=o.splice(u,1);o.splice(w,0,n),this._setActiveStops(o)}this._dragStop=null,this._dragFrac=null,window.removeEventListener("pointermove",this._onStopMove),window.removeEventListener("pointerup",this._onStopUp)};_applyGradient(){let r=this._config?.entity;if(!this.hass||!r)return;let u=Zr(ur(this._stops.map(a),J));this.hass.callService("ha_govee_led_ble","paint_segments",{groups:u},{entity_id:r})}_applyPreset(r){let u=this._config?.entity;if(!this.hass||!u)return;this.hass.callService("ha_govee_led_ble","paint_segments",{groups:ku(r)},{entity_id:u})}_presetSwatch(r){if(r.length===1){let[w,o,n]=r[0];return`rgb(${w},${o},${n})`}return`linear-gradient(90deg, ${r.map(([w,o,n],b)=>`rgb(${w},${o},${n}) ${b/(r.length-1)*100}%`).join(", ")})`}async _saveCurrent(){let r=this._config?.entity;if(!this.hass||!r)return;let u=this._effectName.trim();try{await this.hass.callService("ha_govee_led_ble","save_effect",{name:u,capture_current:!0},{entity_id:r}),this._effectName="",this._feedback={kind:"info",text:`Saved "${u}".`}}catch(w){this._feedback={kind:"error",text:Q(w)}}}_currentStudioContent(){if(this._studioKind==="static")return Bu(this._staticColors.map((r)=>r===null?null:a(r)),this._staticBrightness);if(this._studioKind==="gradient")return au(this._studioStops.map(a));if(this._studioKind==="sketch")return zr(this._sketchColors.map((r)=>r===null?null:a(r)),this._sketchMotion,this._sketchSpeed,this._sketchBrightness,a(this._sketchBackground));if(this._studioKind==="flat")return wu(this._flatFamily,this._flatVariant,this._flatSpeed,this._flatPalette.map(a));if(this._studioKind==="combo")return ou(this._comboEffects.map((r)=>[r.family,r.variant]),this._comboSpeed,this._comboPalette.map(a),this._comboVariant);throw Error(`The ${this._studioKind} editor is not available yet.`)}_currentContentSignature(){try{return JSON.stringify(this._currentStudioContent())}catch{return null}}_targetModel(){let r=this._config?.entity;if(!r||!this.hass)return null;let u=this.hass.entities?.[r]?.device_id;if(!u)return null;return this.hass.devices?.[u]?.model??null}_knownEffectNames(r){let u=this._config?.entity,w=u?this.hass?.states[u]?.attributes?.effect_list:void 0;return[...Array.isArray(w)?w.filter((n)=>typeof n==="string"):[],...r.map((n)=>n.name)]}_loadDraft(r,u,w){if(this._editingId=w,this._loadedContent=u,this._studioName=r,this._studioKind=uu(u),this._selection=X(),this._cursor=1,u.kind==="segments")this._staticColors=Array.from({length:J},(o,n)=>{let b=u.colors[n];return b===void 0||b===null?null:Z(b)}),this._staticBrightness=u.brightness===null?null:Array.from({length:J},(o,n)=>u.brightness?.[n]??null);else if(u.kind==="vibrant")this._studioStops=u.stops.map(Z);else if(u.kind==="sketch")this._sketchColors=Array.from({length:J},(o,n)=>{let b=u.colors[n];return b===void 0||b===null?null:Z(b)}),this._sketchMotion=u.motion,this._sketchSpeed=u.speed,this._sketchBrightness=u.brightness,this._sketchBackground=Z(u.background);else if(u.kind==="flat")Y(u.family),this._flatFamily=u.family,this._flatVariant=u.variant,this._flatSpeed=u.speed,this._flatPalette=u.palette.map(Z);else if(u.kind==="combo"){for(let[o,n]of u.effects)f(o,n);this._comboEffects=u.effects.map(([o,n])=>({family:o,variant:n})),this._comboVariant=u.variant,this._comboSpeed=u.speed,this._comboPalette=u.palette.map(Z)}this._tab="studio",this._pendingDraft=null,this._editingOriginalName=w===null?null:r.trim(),this._editingOriginalContent=w===null?null:JSON.stringify(u),this._draftBaseline=w===null?"":this._draftSignature()}_resetStudioDraft(){this._editingId=null,this._editingOriginalName=null,this._editingOriginalContent=null,this._loadedContent=null,this._studioName="",this._staticColors=Array.from({length:J},()=>null),this._staticBrightness=null,this._studioStops=[...h],this._resetSketch(),this._resetFlat(),this._resetCombo(),this._selection=X(),this._cursor=1,this._pendingDraft=null,this._draftBaseline=this._draftSignature()}_cancelEdit(){this._resetStudioDraft(),this._feedback={kind:"info",text:"Edit cancelled."}}_offerDraft(r,u,w,o,n=!1){if(this._hasUnsavedDraft()){this._pendingDraft={name:r,content:u,editingId:w,feedback:o,clearImport:n},this.updateComplete.then(()=>{this.renderRoot.querySelector(".keep-draft")?.focus()});return}if(this._loadDraft(r,u,w),n)this._importText="";this._feedback={kind:"info",text:o}}_confirmDraftReplacement(){let r=this._pendingDraft;if(r===null)return;if(this._loadDraft(r.name,r.content,r.editingId),r.clearImport)this._importText="";this._feedback={kind:"info",text:r.feedback}}_keepDraft(){this._pendingDraft=null,this._feedback={kind:"info",text:"Kept the existing Studio draft."}}async _saveStudio(){let r=this._config?.entity;if(!this.hass||!r)return;let u=this._studioName.trim();try{let w=this._currentStudioContent(),o=this._editingId;if(o===null)await this.hass.callService("ha_govee_led_ble","save_effect",{name:u,content:w},{entity_id:r}),this._feedback={kind:"info",text:`Saved "${u}".`};else{let n={id:o};if(this._editingOriginalName===null||u!==this._editingOriginalName)n.name=u;if(this._editingOriginalContent===null||JSON.stringify(w)!==this._editingOriginalContent)n.content=w;if(Object.keys(n).length===1){this._feedback={kind:"info",text:"No changes to update."};return}await this.hass.callService("ha_govee_led_ble","update_effect",n,{entity_id:r}),this._feedback={kind:"info",text:`Updated "${u}".`}}this._resetStudioDraft()}catch(w){this._feedback={kind:"error",text:Q(w)}}}async _readEffect(r,u,w){let o=this._config?.entity;if(!this.hass||!o)throw Error("The light is unavailable.");this._busyKey=`${u}:${r.id}`;try{let n=await this.hass.callService("ha_govee_led_ble","export_effect",{id:r.id},{entity_id:o},!0,!0);return w(n.response,o)}finally{this._busyKey=null}}async _editEffect(r){this._feedback=null;try{let u=await this._readEffect(r,"edit",ar);this._offerDraft(u.name,u.content,u.id,`Editing "${u.name}".`)}catch(u){this._feedback={kind:"error",text:Q(u)}}}async _duplicateEffect(r,u){this._feedback=null;try{let w=await this._readEffect(r,"duplicate",ar),o=jr(w.name,this._knownEffectNames(u));this._offerDraft(o,w.content,null,`Loaded "${o}" as a new draft. Review it, then save.`)}catch(w){this._feedback={kind:"error",text:Q(w)}}}async _exportEffect(r){this._feedback=null;try{let u=await this._readEffect(r,"export",er),w=tr(u),o=new Blob([`${JSON.stringify(w,null,2)}
`],{type:"application/json"}),n=URL.createObjectURL(o),b=Ou($u(u.name),n);window.document.body.append(b),b.click(),b.remove(),URL.revokeObjectURL(n),this._feedback={kind:"info",text:`Exported "${u.name}".`}}catch(u){this._feedback={kind:"error",text:Q(u)}}}_chooseImportFile(){this.renderRoot.querySelector(".import-file")?.click()}async _loadImportFile(r){let u=r.target,w=u.files?.[0];if(u.value="",!w)return;try{this._importText=await w.text(),this._feedback={kind:"info",text:`Loaded ${w.name}. Review the JSON, then import it.`}}catch(o){this._feedback={kind:"error",text:Q(o,"Could not read that file.")}}}_reviewImport(r){let u=this._segmentColors()?.length??J;try{let w=ru(this._importText,{model:this._targetModel(),segmentCount:u}),o=pu(w.effect.name,this._knownEffectNames(r));this._offerDraft(o,w.effect.content,null,o===w.effect.name?`Imported "${o}" as a draft. Review it, then save.`:`Imported as "${o}" because that name already exists. Review it, then save.`,!0)}catch(w){this._feedback={kind:"error",text:Q(w,"Could not import that effect.")}}}async _applyEffect(r){let u=this._config?.entity;if(!this.hass||!u)return;this._feedback=null;try{await this.hass.callService("light","turn_on",{effect:r.name},{entity_id:u})}catch(w){this._feedback={kind:"error",text:Q(w)}}}_startRename(r){this._feedback=null,this._deletingId=null,this._renamingId=r.id,this._renameValue=r.name,this.updateComplete.then(()=>{let u=this.renderRoot.querySelector(".rename-input");u?.focus(),u?.select()})}_cancelRename(){this._renamingId=null,this._renameValue=""}async _commitRename(r){let u=this._config?.entity;if(!this.hass||!u)return;let w=this._renameValue.trim();try{if(await this.hass.callService("ha_govee_led_ble","rename_effect",{id:r.id,to:w},{entity_id:u}),this._editingId===r.id&&this._editingOriginalName!==null&&this._studioName.trim()===this._editingOriginalName){let o=this._currentContentSignature()===this._editingOriginalContent;if(this._studioName=w,this._editingOriginalName=w,o)this._draftBaseline=this._draftSignature()}this._renamingId=null,this._renameValue="",this._feedback={kind:"info",text:`Renamed to "${w}".`}}catch(o){this._feedback={kind:"error",text:Q(o)}}}_askDelete(r){if(this._feedback=null,this._renamingId===r.id)this._cancelRename();this._deletingId=r.id,this.updateComplete.then(()=>{this.renderRoot.querySelector(".confirm-cancel")?.focus()})}_cancelDelete(){this._deletingId=null}_onDeleteKey(r){if(r.key==="Escape")r.preventDefault(),this._cancelDelete()}async _deleteEffect(r){let u=this._config?.entity;if(!this.hass||!u)return;this._deletingId=null;try{if(await this.hass.callService("ha_govee_led_ble","delete_effect",{id:r.id},{entity_id:u}),this._editingId===r.id)this._editingId=null,this._editingOriginalName=null,this._editingOriginalContent=null,this._draftBaseline="",this._feedback={kind:"info",text:`Deleted "${r.name}". Its Studio draft was kept as a new effect.`};else this._feedback={kind:"info",text:`Deleted "${r.name}".`};if(this._pendingDraft?.editingId===r.id)this._pendingDraft={...this._pendingDraft,editingId:null,feedback:`Loaded "${r.name}" as a new draft because the saved effect was deleted.`}}catch(w){this._feedback={kind:"error",text:Q(w)}}}_onSaveKey(r,u){if(r.key==="Enter")r.preventDefault(),u()}_onRenameKey(r,u){if(r.key==="Enter")r.preventDefault(),this._commitRename(u);else if(r.key==="Escape")r.preventDefault(),this._cancelRename()}_drawNowPreview(){let r=this.renderRoot?.querySelector("canvas.preview");if(r)this._draw(r)}_draw(r){let u=window.devicePixelRatio||1,w=r.clientWidth||480,o=r.clientHeight||44;if(r.width!==Math.round(w*u))r.width=Math.round(w*u),r.height=Math.round(o*u);let n=r.getContext("2d");if(!n)return;n.setTransform(u,0,0,u,0,0),n.clearRect(0,0,w,o);let b=this._stops.map(a),p=J,k=3,m=(w-k*(p-1))/p;for(let B=0;B<p;B++){let E=rr(b,B/(p-1));n.fillStyle=`rgb(${E.map((j)=>Math.round(j)).join(",")})`;let R=B*(m+k);n.beginPath(),n.roundRect(R,0,m,o,4),n.fill()}}render(){if(!this._config)return q;let r=this._config.entity;if(!r)return this._notice("Select a light entity in the card configuration.");let u=this.hass?.states?.[r];if(!u||u.state==="unavailable"||u.state==="unknown")return this._notice(`${r} is unavailable.`);let w=this._segmentColors();if(!w)return this._notice(`${r} exposes no segment colours; this model has no addressable segments.`);return $`
      <ha-card>
        ${this._renderHeader(u)}
        <div class="body">
          ${this._tab==="now"?this._renderNow(w):q}
          ${this._tab==="studio"?this._renderStudio():q}
          ${this._tab==="library"?this._renderLibrary(u):q}
        </div>
      </ha-card>
    `}_notice(r){return $`
      <ha-card header=${zu}>
        <div class="notice">${r}</div>
      </ha-card>
    `}_renderHeader(r){let u=typeof r.attributes?.effect==="string"&&r.attributes.effect!==""?r.attributes.effect:r.state==="on"?"Colour":"Off";return $`
      <div class="card-head">
        <div class="title">${zu}</div>
        <div class="status">
          <span>Current:</span>
          <span class="current">${u}</span>
        </div>
        <div class="tabs" role="tablist" aria-label="Effect Studio sections">
          ${U.map((w)=>$`
              <button
                class="tab ${this._tab===w.id?"active":""}"
                id=${`tab-${w.id}`}
                role="tab"
                aria-selected=${this._tab===w.id?"true":"false"}
                aria-controls=${`panel-${w.id}`}
                tabindex=${this._tab===w.id?"0":"-1"}
                @click=${()=>this._selectTab(w.id)}
                @keydown=${this._onTabKey}
              >
                ${w.label}
              </button>
            `)}
        </div>
        ${this._feedback?$`<div class="feedback ${this._feedback.kind}" role="alert">
              ${this._feedback.text}
            </div>`:q}
        ${this._pendingDraft?$`
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
    `}_renderScopeBand(r){return $`
      <div class="scope-band ${r}" role="note">
        <span class="dot" aria-hidden="true"></span>
        <span>${r==="live"?"Applies to the strip — changes show instantly":"Draft — builds a saved effect and never changes the strip"}</span>
      </div>
    `}_renderNow(r){let u=Array.from({length:J},(w,o)=>{let n=r[o];return n?Z(n):null});return $`
      <div id="panel-now" role="tabpanel" aria-labelledby="tab-now">
        ${this._renderScopeBand("live")}
        <section>
          <div class="row heading">
            <span class="label">Segment painter</span>
            <span class="hint">${this._selection.size} selected</span>
          </div>
          ${this._renderStrip(u,"off")}
          <div class="row controls">
            <input
              type="color"
              aria-label="Paint colour"
              .value=${this._paintColor}
              @input=${(w)=>this._paintColor=w.target.value}
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
    `}_renderStrip(r,u,w=null){let o=(b)=>`segment-cell-${this._tab}-${this._studioKind}-${b}`,n=[];for(let b=1;b<=J;b++){let p=r[b-1]??null,k=this._selection.has(b),m=b===this._cursor,B=p?"painted":u==="off"?"off":u==="background"?"background":"unchanged",E=p?`background:${p}`:u==="background"&&w!==null?`--cell-background:${w}`:"";n.push($`
        <div
          id=${o(b)}
          class="cell ${k?"sel":""} ${m?"cursor":""} ${p?"":u}"
          style=${E}
          role="option"
          aria-selected=${k?"true":"false"}
          aria-label=${`Segment ${b}, ${B}`}
          title=${`Segment ${b}`}
        >
          <span class="cell-num">${b}</span>
        </div>
      `)}return $`
      <div class="strip-scroll">
        <div
          class="strip"
          style="grid-template-columns: repeat(${J}, 1fr)"
          tabindex="0"
          role="listbox"
          aria-multiselectable="true"
          aria-activedescendant=${o(this._cursor)}
          aria-label=${`Segment painter, ${J} segments`}
          @pointerdown=${this._onDown}
          @keydown=${this._onKey}
        >
          ${n}
        </div>
      </div>
    `}_renderGradient(){return $`
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
    `}_renderStopEditor(){let r=this._activeStops(),u=r.length,w=`linear-gradient(90deg, ${r.map((o,n)=>`${o} ${n/(u-1)*100}%`).join(", ")})`;return $`
      <div class="row heading">
        <span class="label">Gradient stops</span>
        <span class="hint">${u} of ${Fr} to ${Wr}</span>
      </div>
      <div class="gradient-track">
        <div class="gradient-bar" style="background:${w}">
          ${r.map((o,n)=>$`
              <div
                class="handle ${this._dragStop===n?"dragging":""}"
                style="left:${this._dragStop===n&&this._dragFrac!==null?this._dragFrac*100:n/(u-1)*100}%;background:${o}"
                @pointerdown=${(b)=>this._startStopDrag(b,n)}
                title=${`Stop ${n+1}`}
              ></div>
            `)}
        </div>
      </div>
      <div class="stops">
        ${r.map((o,n)=>$`
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
                ?disabled=${n===u-1}
                @click=${()=>this._moveStop(n,1)}
                aria-label=${`Move stop ${n+1} right`}
              >
                →
              </button>
              <button
                class="btn tiny"
                ?disabled=${u<=Fr}
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
          ?disabled=${u>=Wr}
          @click=${this._addStop}
          aria-label="Add stop"
          title="Add stop"
        >
          +
        </button>
      </div>
    `}_renderPresets(){return $`
      <section>
        <div class="row heading">
          <span class="label">Presets</span>
        </div>
        <div class="row presets">
          ${mu.map((r)=>$`
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
    `}_renderSaveCurrent(){return $`
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
    `}_renderStudio(){return $`
      <div id="panel-studio" role="tabpanel" aria-labelledby="tab-studio">
        ${this._renderScopeBand("draft")}
        <section>
          <div class="row heading">
            <span class="label">Effect kind</span>
          </div>
          <div class="kinds" role="radiogroup" aria-label="Effect kind" @keydown=${this._onKindKey}>
            ${or.map((r)=>$`
                <button
                  class="kind ${this._studioKind===r.id?"active":""}"
                  role="radio"
                  aria-checked=${this._studioKind===r.id?"true":"false"}
                  tabindex=${this._studioKind===r.id?"0":"-1"}
                  ?disabled=${this._editingId!==null&&this._studioKind!==r.id}
                  @click=${()=>this._selectKind(r.id)}
                >
                  ${r.label}
                </button>
              `)}
          </div>
          ${ju.length>0?$`
                <div class="kinds-soon">
                  <span>Coming next:</span>
                  ${ju.map((r)=>$`
                      <button class="kind soon" disabled aria-disabled="true">
                        ${r.label}<span class="soon-tag">soon</span>
                      </button>
                    `)}
                </div>
              `:q}
        </section>
        ${this._studioKind==="static"?this._renderStaticEditor():this._studioKind==="gradient"?this._renderGradientAuthor():this._studioKind==="sketch"?this._renderSketchAuthor():this._studioKind==="flat"?this._renderFlatAuthor():this._studioKind==="combo"?this._renderComboAuthor():this._renderPendingAuthor()}
      </div>
    `}_renderStaticEditor(){let r=this._staticColors.filter((w)=>w!==null).length,u=Ru(this._staticColors.map((w)=>w===null?null:a(w)),this._staticBrightness);return $`
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
            @input=${(w)=>this._paintColor=w.target.value}
          />
          <button class="btn primary" @click=${this._paintStatic}>Paint selected</button>
          <button class="btn" @click=${this._setUnchangedStatic}>Clear selected</button>
          <button class="btn" @click=${this._selectAll}>Select all</button>
          <button class="btn" @click=${this._resetStatic}>Reset</button>
        </div>
        <p class="help">
          Paint a colour onto chosen segments; hatched segments are left as they are on the strip.
        </p>
        ${this._renderStudioSave(u,"Paint at least one segment to save.")}
      </section>
    `}_renderSketchAuthor(){let r=this._sketchColors.filter((o)=>o!==null).length,u=zr(this._sketchColors.map((o)=>o===null?null:a(o)),this._sketchMotion,this._sketchSpeed,this._sketchBrightness,a(this._sketchBackground)),w=nu(u).map(Z);return $`
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
          ${t.map((o)=>$`
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
        ${this._renderPreviewStrip(w)}
        ${this._renderStudioSave(!0,"")}
      </section>
    `}_renderPaletteEditor(r,u,w,o,n,b,p){return $`
      <div class="row heading">
        <span class="label">${w}</span>
        <span class="hint">${r.length} of ${u}</span>
      </div>
      <div class="palette-editor">
        ${r.map((k,m)=>$`
            <div class="palette-chip">
              <span class="palette-number">${m+1}</span>
              <input
                type="color"
                aria-label=${`${w} colour ${m+1}`}
                .value=${k}
                @input=${(B)=>o(m,B.target.value)}
              />
              <button
                class="btn tiny"
                ?disabled=${m===0}
                @click=${()=>p(m,-1)}
                aria-label=${`Move colour ${m+1} left`}
              >
                ←
              </button>
              <button
                class="btn tiny"
                ?disabled=${m===r.length-1}
                @click=${()=>p(m,1)}
                aria-label=${`Move colour ${m+1} right`}
              >
                →
              </button>
              <button
                class="btn tiny danger"
                @click=${()=>b(m)}
                aria-label=${`Remove colour ${m+1}`}
              >
                ×
              </button>
            </div>
          `)}
        <button
          class="btn palette-add"
          ?disabled=${r.length>=u}
          @click=${n}
        >
          Add colour
        </button>
      </div>
    `}_renderFlatAuthor(){let r=Y(this._flatFamily),u=this._flatPalette.length===0?[]:Array.from({length:J},(w,o)=>this._flatPalette[o%this._flatPalette.length]);return $`
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
          ${z.map((w)=>$`
              <button
                class="family ${w.family===this._flatFamily?"active":""}"
                role="radio"
                aria-checked=${w.family===this._flatFamily?"true":"false"}
                tabindex=${w.family===this._flatFamily?"0":"-1"}
                @click=${()=>this._selectFlatFamily(w.family)}
              >
                ${w.label}
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
          ${r.variants.map((w)=>$`
              <button
                class="variant ${w.variant===this._flatVariant?"active":""}"
                role="radio"
                aria-checked=${w.variant===this._flatVariant?"true":"false"}
                tabindex=${w.variant===this._flatVariant?"0":"-1"}
                @click=${()=>this._flatVariant=w.variant}
              >
                ${w.label}
              </button>
            `)}
        </div>
        <p class="help">${r.description}</p>
      </section>
      <section>
        ${this._renderPaletteEditor(this._flatPalette,r.palette_max,"Shared palette order",(w,o)=>this._setFlatPaletteColour(w,o),()=>this._addFlatPaletteColour(),(w)=>this._removeFlatPaletteColour(w),(w,o)=>this._moveFlatPaletteColour(w,o))}
        ${u.length>0?$`
              <div class="row heading">
                <span class="label">Representative preview</span>
                <span class="preview-badge">Approximate · animated on device</span>
              </div>
              ${this._renderPreviewStrip(u)}
            `:$`<p class="help">Add at least one colour to preview and save this effect.</p>`}
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
            @input=${(w)=>this._flatSpeed=Number(w.target.value)}
          />
          <output>${this._flatSpeed}%</output>
        </label>
        <button class="btn" @click=${this._resetFlat}>Reset Flat draft</button>
        ${this._renderStudioSave(this._flatPalette.length>0,"Add at least one palette colour to save.")}
      </section>
    `}_renderComboAuthor(){let r=this._comboPalette.length===0?[]:Array.from({length:J},(u,w)=>this._comboPalette[w%this._comboPalette.length]);return $`
      <section>
        <div class="row heading">
          <span class="label">Effect chain</span>
          <span class="hint">${this._comboEffects.length} of 4 steps</span>
        </div>
        ${this._comboEffects.length===0?$`<p class="help">Add at least one Flat effect to the chain.</p>`:$`
              <ol class="combo-chain">
                ${this._comboEffects.map((u,w)=>{let o=Y(u.family);return $`
                    <li class="combo-step">
                      <span class="combo-number">${w+1}</span>
                      <label>
                        <span class="sr-only">Step ${w+1} family</span>
                        <select
                          aria-label=${`Step ${w+1} family`}
                          .value=${String(u.family)}
                          @change=${(n)=>this._setComboFamily(w,Number(n.target.value))}
                        >
                          ${z.map((n)=>$`
                              <option value=${String(n.family)}>${n.label}</option>
                            `)}
                        </select>
                      </label>
                      <label>
                        <span class="sr-only">Step ${w+1} variant</span>
                        <select
                          aria-label=${`Step ${w+1} variant`}
                          .value=${String(u.variant)}
                          @change=${(n)=>this._setComboVariant(w,Number(n.target.value))}
                        >
                          ${o.variants.map((n)=>$`
                              <option value=${String(n.variant)}>${n.label}</option>
                            `)}
                        </select>
                      </label>
                      <div class="combo-actions">
                        <button
                          class="btn tiny"
                          ?disabled=${w===0}
                          @click=${()=>this._moveComboStep(w,-1)}
                          aria-label=${`Move step ${w+1} up`}
                        >
                          ↑
                        </button>
                        <button
                          class="btn tiny"
                          ?disabled=${w===this._comboEffects.length-1}
                          @click=${()=>this._moveComboStep(w,1)}
                          aria-label=${`Move step ${w+1} down`}
                        >
                          ↓
                        </button>
                        <button
                          class="btn tiny danger"
                          @click=${()=>this._removeComboStep(w)}
                          aria-label=${`Remove step ${w+1}`}
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
        ${this._renderPaletteEditor(this._comboPalette,8,"Shared palette order",(u,w)=>this._setComboPaletteColour(u,w),()=>this._addComboPaletteColour(),(u)=>this._removeComboPaletteColour(u),(u,w)=>this._moveComboPaletteColour(u,w))}
        ${r.length>0?$`
              <div class="row heading">
                <span class="label">Sequence preview</span>
                <span class="preview-badge">Approximate · animated on device</span>
              </div>
              ${this._renderPreviewStrip(r)}
            `:$`<p class="help">Add at least one shared palette colour.</p>`}
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
            @input=${(u)=>this._comboSpeed=Number(u.target.value)}
          />
          <output>${this._comboSpeed}%</output>
        </label>
        <button class="btn" @click=${this._resetCombo}>Reset Combo draft</button>
        ${this._renderStudioSave(this._comboEffects.length>0&&this._comboPalette.length>0,this._comboEffects.length===0?"Add at least one effect step to save.":"Add at least one shared palette colour to save.")}
      </section>
    `}_renderPendingAuthor(){let r=wr.find((w)=>w.id===this._studioKind)?.label??this._studioKind,u=this._loadedContent?.kind===this._studioKind;return $`
      <section class="pending-author">
        <div class="row heading">
          <span class="label">${r}</span>
          <span class="hint">Editor coming next</span>
        </div>
        <p class="help">
          ${u?`This ${r} effect is loaded safely, but this editor is not available in the current build.`:`The ${r} editor will be enabled in the next Studio phase.`}
        </p>
        ${this._editingId!==null?$`<button class="btn" @click=${this._cancelEdit}>Cancel edit</button>`:q}
      </section>
    `}_renderGradientAuthor(){let r=ur(this._studioStops.map(a),J).map(Z);return $`
      <section>
        ${this._renderStopEditor()}
        <div class="row heading">
          <span class="label">Draft preview · ${J} segments</span>
        </div>
        ${this._renderPreviewStrip(r)}
        <p class="help">Saves the colour stops as a gradient effect.</p>
        ${this._renderStudioSave(!0,"")}
      </section>
    `}_renderPreviewStrip(r){return $`
      <div class="strip-scroll">
        <div
          class="strip preview-strip"
          style="grid-template-columns: repeat(${J}, 1fr)"
          aria-hidden="true"
        >
          ${r.map((u,w)=>$`
              <div class="cell" style="background:${u}" title=${`Segment ${w+1}`}>
                <span class="cell-num">${w+1}</span>
              </div>
            `)}
        </div>
      </div>
    `}_renderStudioSave(r,u){let w=this._studioName.trim()!=="",o=this._editingId!==null;return $`
      ${o?$`<div class="edit-band" role="status">
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
          ?disabled=${!w||!r}
          @click=${this._saveStudio}
        >
          ${o?"Update effect":"Save effect"}
        </button>
      </div>
      ${!r&&u!==""?$`<p class="help">${u}</p>`:q}
    `}_renderLibrary(r){let u=Dr(r.attributes?.custom_effects),w=typeof r.attributes?.effect==="string"?r.attributes.effect:null;return $`
      <div id="panel-library" role="tabpanel" aria-labelledby="tab-library">
        <section>
          <div class="row heading">
            <span class="label">Saved effects</span>
            <span class="hint">${u.length} saved</span>
          </div>
          ${u.length===0?$`<p class="help">
                No custom effects saved yet. Create one in the Studio tab, or snapshot the strip from
                the Now tab.
              </p>`:$`
                <p class="help">Select an effect to apply it.</p>
                <ul class="effects" role="list">
                  ${u.map((o)=>this._renderEffectRow(o,w,u))}
                </ul>
              `}
        </section>
        <section>
          <details class="import-panel">
            <summary>Import effect JSON</summary>
            <div class="import-body">
              <textarea
                class="import-json"
                aria-label="Effect JSON"
                placeholder="Paste an exported Govee effect here"
                .value=${this._importText}
                @input=${(o)=>this._importText=o.target.value}
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
                  @click=${()=>this._reviewImport(u)}
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
    `}_renderEffectRow(r,u,w){if(this._renamingId===r.id)return $`
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
      `;if(this._deletingId===r.id)return $`
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
      `;let o=u!==null&&u===r.name,n=this._busyKey?.endsWith(`:${r.id}`)??!1;return $`
      <li class="effect ${o?"active":""}">
        <div class="effect-main">
          ${o?$`<span class="badge-active" aria-current="true">✓ Active</span>`:$`<button
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
            @click=${()=>void this._duplicateEffect(r,w)}
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
    `}static styles=vr}customElements.define("govee-led-ble-card",Yu);window.customCards=window.customCards||[];window.customCards.push({type:"govee-led-ble-card",name:"Govee LED BLE",description:"Paint, compose and save custom effects for a segment-capable Govee LED BLE light.",preview:!1});console.info("%c govee-led-ble-card ","background:#1982c4;color:#fff;border-radius:3px","loaded");
