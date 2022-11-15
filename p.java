    package tiktak;

    public class p {
        public static void main(String[] args) throws InterruptedException{


           Phone phone=new Phone("87002433243","iphone","bob","black","8403033203","200gramm");
           Phone phone2=new Phone("456455243","recovery","rob","black","8403033203","200gramm");
           Phone phone3=new Phone("54633243","xaml","Anatoly","black","8403033203","200gramm");
           Phone phone4=new Phone("54562433243","bobus","Thag","black","870551312","200gramm");
           Phone phone5=new Phone("8442433243","samsung","Robert","black","8707564245","200gramm");

           Phone phone6 =new Phone("38838383","robert","x5","220");
           Phone phone7 =new Phone("82323323","s3");
            System.out.println(phone.getColorPhone());
            System.out.println(phone2.getNumber());
            System.out.println(phone3.getRecieverPhone());
            System.out.println(phone4.getWeight());
            System.out.println(phone5.getModel());
            System.out.println(phone.getRecieverPhone());
            phone.setColorPhone("white");
            phone2.setModel("bukigang");
            phone3.setWeight("230");

            phone2.recieveCall("boby","8329393939");
            phone2.sendMessage();
        }
    }
