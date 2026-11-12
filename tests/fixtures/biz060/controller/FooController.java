package kr.co.kfs.asseterp.biz.foo.controller;

import org.springframework.web.bind.annotation.*;
import java.time.LocalDate;
import java.util.List;
import kr.co.kfs.asseterp.biz.foo.dto.FooReq;
import kr.co.kfs.asseterp.biz.foo.service.FooService;

@RestController
@RequestMapping("/api/v1/foo/bars")
public class FooController {

    private final FooService fooService;

    public FooController(FooService fooService) {
        this.fooService = fooService;
    }

    @GetMapping
    public List<Object> list(
            @RequestParam(required = false) Long personId,
            @RequestParam LocalDate baseDate
    ) {
        return fooService.search(personId, baseDate);
    }

    @PutMapping("/{id}/time")
    public int updateTime(
            @PathVariable Long id,
            @RequestBody FooReq req
    ) {
        return fooService.updateTime(id, req);
    }

    @DeleteMapping
    public int delete(
            @RequestBody List<Long> ids
    ) {
        return fooService.deleteList(ids);
    }

    @PutMapping("/{id}/appr")
    public int updateAppr(
            @PathVariable Long id,
            @RequestParam Long apprId
    ) {
        return fooService.updateAppr(id, apprId);
    }
}
