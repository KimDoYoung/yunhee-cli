package biz.pay.controller;

import org.springframework.web.bind.annotation.*;
import java.util.List;

@RestController
@RequestMapping("/api/v1/pay/work-times")
public class PayWorkTimeController {

    private final PayWorkTimeService payWorkTimeService;

    public PayWorkTimeController(PayWorkTimeService payWorkTimeService) {
        this.payWorkTimeService = payWorkTimeService;
    }

    @GetMapping
    public List<PayWorkTimeRes> search() {
        return payWorkTimeService.search();
    }

    @PutMapping
    public void save(@RequestBody List<PayWorkTimeSaveReq> reqs) {
        payWorkTimeService.save(reqs);
    }

    @DeleteMapping
    public void delete(@RequestBody List<Long> ids) {
        payWorkTimeService.delete(ids);
    }
}
