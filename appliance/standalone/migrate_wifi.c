/* Move saved WPA-PSK configuration only on the owner's tablet. Never emits
 * SSIDs or secrets. No host transfer, debug logging or arbitrary input paths.
 */
#define _GNU_SOURCE
#include <errno.h>
#include <ctype.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <unistd.h>

static int decode(const char *begin,const char *end,char *out,size_t cap) {
    size_t used=0;
    while(begin<end) {
        unsigned char c=(unsigned char)*begin++;
        if(c=='&') {
            static const char *entity[]={"quot;","apos;","amp;","lt;","gt;"};
            static const char value[]={'"','\'','&','<','>'};
            int found=0;
            for(unsigned i=0;i<5;i++)if((size_t)(end-begin)>=strlen(entity[i])&&
                    !memcmp(begin,entity[i],strlen(entity[i]))) {
                c=(unsigned char)value[i];begin+=strlen(entity[i]);found=1;break;
            }
            if(!found)return -1;
        }
        if(c<32||c==127||used+1>=cap)return -1;
        out[used++]=(char)c;
    }
    out[used]=0;return (int)used;
}
static int field(const char *start,const char *end,const char *key,char *out,size_t cap) {
    char tag[80];snprintf(tag,sizeof tag,"<string name=\"%s\">",key);
    const char *p=strstr(start,tag);if(!p||p>=end)return -1;
    p+=strlen(tag);const char *q=strstr(p,"</string>");
    if(!q||q>end)return -1;
    return decode(p,q,out,cap);
}
static int unquote(char *s) {
    size_t n=strlen(s);if(n<2||s[0]!='"'||s[n-1]!='"')return -1;
    memmove(s,s+1,n-2);s[n-2]=0;return (int)n-2;
}
int main(void) {
    const char *source="/data/misc/wifi/WifiConfigStore.xml";
    const char *target="/data/forge-standalone/wpa_supplicant.conf";
    const char *temp="/data/forge-standalone/wpa_supplicant.conf.new";
    if(geteuid()!=0)return 77;
    int fd=open(source,O_RDONLY|O_CLOEXEC|O_NOFOLLOW);struct stat st;
    if(fd<0){perror("Wi-Fi input open");return 1;}
    if(fstat(fd,&st)){perror("Wi-Fi input stat");close(fd);return 1;}
    if(!S_ISREG(st.st_mode)||st.st_size<1||st.st_size>2097152){fputs("Wi-Fi input shape invalid\n",stderr);close(fd);return 1;}
    char *xml=calloc(1,(size_t)st.st_size+1);if(!xml)return 1;
    size_t used=0;while(used<(size_t)st.st_size){ssize_t n=read(fd,xml+used,(size_t)st.st_size-used);if(n<=0){perror("Wi-Fi input read");close(fd);free(xml);return 1;}used+=(size_t)n;}close(fd);
    fd=open(temp,O_WRONLY|O_CREAT|O_EXCL|O_CLOEXEC|O_NOFOLLOW,0600);
    if(fd<0){perror("Wi-Fi output open");free(xml);return 1;}FILE *f=fdopen(fd,"w");if(!f){perror("Wi-Fi output stream");close(fd);free(xml);return 1;}
    fputs("ctrl_interface=/run/wpa_supplicant\nupdate_config=0\n",f);
    unsigned count=0,configs=0,ssids=0,keys=0;const char *p=xml;
    while((p=strstr(p,"<WifiConfiguration>"))) {
        const char *end=strstr(p,"</WifiConfiguration>");if(!end)break;
        configs++;
        char ssid[257]={0},psk[257]={0};
        int s=field(p,end,"SSID",ssid,sizeof ssid),k=field(p,end,"PreSharedKey",psk,sizeof psk);
        if(s>=0)ssids++;
        if(k>=0)keys++;
        if(s>=0&&k>=0) {
            int length=unquote(ssid),password=unquote(psk),hex=0;
            if(length<0)length=(int)strlen(ssid);
            if(password<0) {
                password=(int)strlen(psk);
                if(password==64){hex=1;for(int i=0;i<64;i++)if(!isxdigit((unsigned char)psk[i]))hex=0;}
            }
            if(length>0&&length<=32&&((password>=8&&password<=63)||hex)) {
                fputs("network={\n ssid=",f);
                for(int i=0;i<length;i++)fprintf(f,"%02x",(unsigned char)ssid[i]);
                fputs("\n key_mgmt=WPA-PSK\n psk=",f);
                if(!hex)fputc('"',f);
                for(int i=0;i<password;i++){if(!hex&&(psk[i]=='"'||psk[i]=='\\'))fputc('\\',f);fputc(psk[i],f);}
                if(!hex)fputc('"',f);
                fputs("\n}\n",f);count++;
            }
        }
        memset(psk,0,sizeof psk);p=end+strlen("</WifiConfiguration>");
    }
    memset(xml,0,used);free(xml);
    int failed=ferror(f)||fflush(f)||fsync(fd);if(fclose(f))failed=1;
    if(failed||!count){unlink(temp);fprintf(stderr,"Wi-Fi conversion incomplete: %u configs, %u parsed names, %u parsed credentials; output error=%d\n",configs,ssids,keys,failed);return 1;}
    /* This kernel predates renameat2, used by current static Bionic rename(). */
    if(syscall(__NR_renameat,AT_FDCWD,temp,AT_FDCWD,target)){perror("Wi-Fi output rename");unlink(temp);return 1;}
    printf("Saved %u Wi-Fi configuration(s) on the tablet; no credentials exported.\n",count);
    return 0;
}
